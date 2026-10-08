from __future__ import annotations

import json
import os
import random
import subprocess
import tempfile
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

import trimesh

from config import BASE_DIR, GENERATED_DIR, get_category_names, get_setting
from key_rotator import GroqKeyRotator


CATEGORY_DEFINITIONS = {
    "Tabletop Miniatures & D&D Figurines": {
        "keywords": ["miniature", "figurine", "dnd", "fantasy", "male/female", "balanced proportions"],
        "prompt": "Create a compact tabletop miniature with clean silhouette, visible armor detail, no thin fragile extensions, and printability in FDM resin."
    },
    "Articulated Print-in-Place Toys": {
        "keywords": ["articulated", "print-in-place", "joint", "toy", "dragon", "creature"],
        "prompt": "Create a print-in-place articulated creature with robust hinge joints, limited clearance, and strong material distribution."
    },
    "Home Organizers & Office Accessories": {
        "keywords": ["organizer", "phone stand", "cable management", "desk", "accessory"],
        "prompt": "Design a durable utility organizer or desk accessory with ergonomic proportions and stable support geometry."
    },
    "Resin Jewelry Casting Molds": {
        "keywords": ["jewelry", "mold", "casting", "precision", "sprue", "vibration"],
        "prompt": "Design a high-precision jewelry casting mold with clean draft angles, sprue relief, and print-safe machinable geometry."
    },
    "Dental & Medical Models": {
        "keywords": ["dental", "medical", "surgical guide", "impression", "precision"],
        "prompt": "Design a precise dental or medical model with consistent wall thickness and safe geometric tolerances, intended for print verification."
    },
    "Classic Car Parts & Discontinued Machinery Spares": {
        "keywords": ["car", "spare", "machinery", "classic", "bracket", "adapter"],
        "prompt": "Generate a functional classic car or machinery replacement bracket with realistic mounting geometry and printable strength."
    },
    "Accessibility Aids": {
        "keywords": ["accessibility", "door opener", "pen grip", "handle", "ergonomic"],
        "prompt": "Create an ergonomic accessibility aid with comfortable gripping surfaces and safe, non-fragile geometry."
    },
    "Custom Electronics Enclosures": {
        "keywords": ["electronics", "enclosure", "Arduino", "Raspberry Pi", "PCB", "ventilation"],
        "prompt": "Design a custom electronics enclosure with panel spacing, mounting bosses, ventilation, and reliable printability."
    },
    "Parametric Engineering Fittings & Pipe Connectors": {
        "keywords": ["pipe connector", "adapter", "fitting", "parametric", "threaded", "angle"],
        "prompt": "Design a parametric engineering fitting with robust connector geometry, clear tolerances, and print-safe wall thickness."
    },
}


@dataclass
class GenerationRequest:
    category: str
    count: int = 1
    size_mm: float | None = None
    custom_parameters: dict[str, Any] = field(default_factory=dict)
    preferred_format: str = "openscad"


class STLGenerator:
    def __init__(self, rotator: GroqKeyRotator | None = None) -> None:
        self.rotator = rotator or GroqKeyRotator()

    def random_category(self) -> str:
        categories = list(CATEGORY_DEFINITIONS.keys())
        return random.choice(categories)

    def build_prompt(self, category: str, user_params: dict[str, Any] | None = None) -> str:
        definition = CATEGORY_DEFINITIONS.get(category, CATEGORY_DEFINITIONS[next(iter(CATEGORY_DEFINITIONS))])
        params = user_params or {}
        param_text = "\n".join(f"- {k}: {v}" for k, v in params.items()) if params else "- No extra custom parameters provided"
        return (
            f"You are a senior product designer and CAD engineer. Generate a clean, printable 3D model for the category: {category}.\n"
            f"Design goals: {definition['prompt']}\n"
            f"Use printability-first constraints: wall thickness >= 1.6 mm unless specifically required otherwise, avoid nonmanifold or impossible geometry, and ensure robust supports if needed.\n"
            f"Preferred output format: OpenSCAD if possible, otherwise CadQuery. The code must export directly to STL and include a valid final 'export' or 'projection' step.\n"
            f"Use a realistic model scale in millimeters.\n"
            f"Additional constraints:\n{param_text}\n\n"
            f"Return valid JSON with keys: 'cad_type' ('openscad' or 'cadquery'), 'title', 'description', 'code', and 'notes'.\n"
            f"The code must be self-contained and compilable without additional files."
        )

    def call_llm(self, prompt: str) -> dict[str, Any]:
        payload = {
            "model": get_setting("GROQ_DEFAULT_MODEL", "llama-3.3-70b-versatile"),
            "messages": [
                {"role": "system", "content": "You are a CAD generator for 3D printable models; return strict JSON only."},
                {"role": "user", "content": prompt},
            ],
            "temperature": 0.6,
            "max_tokens": 1600,
        }
        response = self.rotator.request("https://api.groq.com/openai/v1/chat/completions", payload, timeout=90)
        try:
            data = response.json()
            content = data["choices"][0]["message"]["content"]
            if "```" in content:
                content = content.split("```", 2)[1].replace("json", "", 1).strip()
            return json.loads(content)
        except Exception as exc:
            raise RuntimeError(f"Failed to parse Groq output: {exc}") from exc

    def compile_openscad(self, code: str, output_path: Path) -> bool:
        with tempfile.TemporaryDirectory(prefix="openscad_") as tmpdir:
            source_path = Path(tmpdir) / "model.scad"
            source_path.write_text(code, encoding="utf-8")
            cmd = ["openscad", "-o", str(output_path), str(source_path)]
            try:
                subprocess.run(cmd, check=True, capture_output=True, text=True)
                return output_path.exists() and output_path.stat().st_size > 0
            except Exception:
                return False

    def compile_cadquery(self, code: str, output_path: Path) -> bool:
        with tempfile.TemporaryDirectory(prefix="cadquery_") as tmpdir:
            script_path = Path(tmpdir) / "model.py"
            script_path.write_text(code, encoding="utf-8")
            try:
                subprocess.run(["python", str(script_path)], check=True, capture_output=True, text=True)
            except Exception:
                return False
            if output_path.exists() and output_path.stat().st_size > 0:
                return True
            return False

    def validate_mesh(self, stl_path: Path) -> tuple[bool, str]:
        try:
            mesh = trimesh.load_mesh(str(stl_path), force="mesh")
            if not isinstance(mesh, trimesh.Trimesh):
                return False, "Loaded mesh is not a single Trimesh object."
            if not mesh.is_watertight:
                return False, "Mesh is not watertight."
            if mesh.euler_number is None:
                return False, "Mesh topology could not be validated."
            if mesh.is_empty:
                return False, "Mesh is empty."
            return True, "Mesh valid."
        except Exception as exc:
            return False, f"Mesh validation failed: {exc}"

    def generate_model(self, request: GenerationRequest) -> dict[str, Any]:
        category = request.category if request.category else self.random_category()
        base_prompt = self.build_prompt(category, request.custom_parameters)
        llm_data = self.call_llm(base_prompt)
        generated_code = llm_data.get("code", "")
        if not generated_code:
            raise RuntimeError("LLM returned empty CAD code.")

        export_dir = GENERATED_DIR / category.replace("/", "_")
        export_dir.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        file_base = f"{category.replace(' ', '_').replace('/', '_')}_{timestamp}"
        output_path = export_dir / f"{file_base}.stl"

        compile_success = False
        if llm_data.get("cad_type") == "cadquery":
            compile_success = self.compile_cadquery(generated_code, output_path)
        else:
            compile_success = self.compile_openscad(generated_code, output_path)

        if not compile_success:
            fallback_code = self.create_openscad_fallback(category, request.custom_parameters)
            compile_success = self.compile_openscad(fallback_code, output_path)

        if not compile_success:
            raise RuntimeError("CAD code could not be compiled to STL.")

        valid, reason = self.validate_mesh(output_path)
        if not valid:
            if output_path.exists():
                output_path.unlink(missing_ok=True)
            raise RuntimeError(reason)

        return {
            "category": category,
            "file_path": str(output_path),
            "title": llm_data.get("title", file_base),
            "description": llm_data.get("description", "Generated STL"),
            "notes": llm_data.get("notes", ""),
            "valid": True,
            "timestamp": datetime.utcnow().isoformat(),
        }

    def create_openscad_fallback(self, category: str, params: dict[str, Any]) -> str:
        size = float(params.get("size_mm", 50))
        thickness = float(params.get("wall_thickness_mm", 2.0))
        height = float(params.get("height_mm", size * 0.8))
        width = float(params.get("width_mm", size))
        depth = float(params.get("depth_mm", size * 0.6))

        return f"""
        $fn = 42;
        module base_block() {{
            cube([{width}, {depth}, {height}]);
        }}
        module decorative_features() {{
            translate([{width * 0.2}, {depth * 0.2}, 0])
                cylinder(h={height * 0.6}, r={min(width, depth) * 0.15});
        }}
        difference() {{
            base_block();
            translate([{thickness}, {thickness}, {thickness}])
                cube([{width - thickness * 2}, {depth - thickness * 2}, {height}]);
        }}
        decorative_features();
        """


if __name__ == "__main__":
    generator = STLGenerator()
    result = generator.generate_model(GenerationRequest(category="Home Organizers & Office Accessories", count=1, custom_parameters={"size_mm": 80}))
    print(json.dumps(result, indent=2))
