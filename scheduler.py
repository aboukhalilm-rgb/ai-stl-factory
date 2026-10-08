from __future__ import annotations

import json
import random
import subprocess
import tempfile
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

import trimesh

from config import GENERATED_DIR, get_setting
from key_rotator import GroqKeyRotator

CATEGORY_DEFINITIONS = {
    "Tabletop Miniatures & D&D Figurines": {
        "prompt": "Create a clean, robust tabletop miniature/fantasy figurine with a strong silhouette, reasonable wall thickness, and no fragile thin details.",
    },
    "Articulated Print-in-Place Toys": {
        "prompt": "Design a print-in-place articulated creature or toy with working joints, safe clearance, and durable movement geometry.",
    },
    "Home Organizers & Office Accessories": {
        "prompt": "Design a compact functional organizer or desk accessory with ergonomic proportions and reliable support strength.",
    },
    "Resin Jewelry Casting Molds": {
        "prompt": "Create a high-precision jewelry casting mold with sprues, clean draft angles, and printable mold geometry.",
    },
    "Dental & Medical Models": {
        "prompt": "Design a precise dental or medical model with consistent wall thickness, safe tolerances, and realistic anatomical geometry.",
    },
    "Classic Car Parts & Discontinued Machinery Spares": {
        "prompt": "Create a replacement or bracket part for classic machinery with realistic fit, strength, and stable geometry.",
    },
    "Accessibility Aids": {
        "prompt": "Design an ergonomic accessibility helper with comfortable grip surfaces and safe, non-fragile geometry.",
    },
    "Custom Electronics Enclosures": {
        "prompt": "Create a smart electronics enclosure with screw bosses, venting pattern, panel spacing, and clean mounting features.",
    },
    "Parametric Engineering Fittings & Pipe Connectors": {
        "prompt": "Design a parametric fitting or pipe connector with measurable dimensions, clean tolerances, and strong joint features.",
    },
}


@dataclass
class GenerationRequest:
    category: str = ""
    count: int = 1
    size_mm: float | None = None
    custom_parameters: dict[str, Any] = field(default_factory=dict)
    preferred_format: str = "openscad"


class STLGenerator:
    def __init__(self, rotator: GroqKeyRotator | None = None) -> None:
        self.rotator = rotator or GroqKeyRotator()

    def random_category(self) -> str:
        return random.choice(list(CATEGORY_DEFINITIONS.keys()))

    def build_prompt(self, category: str, extra: dict[str, Any] | None = None) -> str:
        definition = CATEGORY_DEFINITIONS.get(category, CATEGORY_DEFINITIONS[next(iter(CATEGORY_DEFINITIONS))])
        params = extra or {}
        param_text = "\n".join(f"- {key}: {value}" for key, value in params.items()) if params else "- No extra custom parameters provided"
        return (
            f"You are a senior CAD designer and STL producer.\n"
            f"Generate a parametric, printable 3D model for category: {category}.\n"
            f"Design goal: {definition['prompt']}\n"
            f"Constraints: wall thickness at least 1.6 mm, avoid fragile spikes, use real-world millimeter dimensions, no self-intersection or impossible geometry.\n"
            f"Additional parameters:\n{param_text}\n\n"
            f"Return valid JSON only with keys: 'cad_type', 'title', 'description', 'code', 'notes'.\n"
            f"cad_type must be either 'openscad' or 'cadquery'.\n"
            f"The code must be self-contained and directly compilable. Use OpenSCAD if possible.\n"
            f"Do not include markdown fences or explanation outside JSON."
        )

    def call_llm(self, prompt: str) -> dict[str, Any]:
        payload = {
            "model": get_setting("GROQ_DEFAULT_MODEL", "llama-3.3-70b-versatile"),
            "messages": [
                {"role": "system", "content": "You are a CAD generation engine for 3D printable products."},
                {"role": "user", "content": prompt},
            ],
            "temperature": 0.4,
            "max_tokens": 1800,
        }
        data = self.rotator.request_json("https://api.groq.com/openai/v1/chat/completions", payload, timeout=90)
        content = data["choices"][0]["message"]["content"]
        if "```" in content:
            content = content.split("```", 2)[1].replace("json", "", 1).strip()
        try:
            return json.loads(content)
        except json.JSONDecodeError as exc:
            raise RuntimeError(f"Groq returned invalid JSON: {content[:500]}") from exc

    def compile_openscad(self, code: str, output_path: Path) -> bool:
        try:
            result = subprocess.run(["openscad", "-o", str(output_path), "-"], input=code, capture_output=True, text=True, timeout=120)
            if result.returncode != 0:
                return False
            return output_path.exists() and output_path.stat().st_size > 0
        except (FileNotFoundError, subprocess.TimeoutExpired):
            return False

    def compile_cadquery(self, code: str, output_path: Path) -> bool:
        with tempfile.TemporaryDirectory(prefix="cadquery_") as tmpdir:
            script_path = Path(tmpdir) / "model.py"
            script_path.write_text(code, encoding="utf-8")
            try:
                proc = subprocess.run(["python", str(script_path)], capture_output=True, text=True, timeout=120)
                if proc.returncode != 0:
                    return False
                return output_path.exists() and output_path.stat().st_size > 0
            except (FileNotFoundError, subprocess.TimeoutExpired):
                return False

    def validate_mesh(self, file_path: Path) -> tuple[bool, str]:
        try:
            mesh = trimesh.load_mesh(str(file_path), force="mesh")
            if not isinstance(mesh, trimesh.Trimesh):
                return False, "The STL file did not resolve to a single mesh object."
            if mesh.is_empty:
                return False, "The mesh is empty."
            if not mesh.is_watertight:
                return False, "The mesh is not watertight."
            if mesh.euler_number is None:
                return False, "Could not validate the topology of the mesh."
            return True, "Mesh passes validation."
        except Exception as exc:
            return False, f"Mesh validation failed: {exc}"

    def create_openscad_fallback(self, category: str, params: dict[str, Any]) -> str:
        size = float(params.get("size_mm", 60))
        width = float(params.get("width_mm", size))
        depth = float(params.get("depth_mm", size * 0.7))
        height = float(params.get("height_mm", size * 0.8))
        wall = float(params.get("wall_thickness_mm", 2.2))

        return f"""
        $fn = 32;
        module body() {{
            cube([{width}, {depth}, {height}]);
        }}
        module recess() {{
            translate([{wall}, {wall}, {wall}])
                cube([{width - wall * 2}, {depth - wall * 2}, {height}]);
        }}
        module accent() {{
            translate([{width * 0.3}, {depth * 0.35}, 0])
                cylinder(h={height * 0.85}, r={min(width, depth) * 0.12});
        }}
        difference() {{
            body();
            recess();
        }}
        accent();
        """

    def compile_generated_code(self, cad_type: str, code: str, output_path: Path) -> bool:
        if cad_type.lower() == "cadquery":
            return self.compile_cadquery(code, output_path)
        return self.compile_openscad(code, output_path)

    def generate_model(self, request: GenerationRequest) -> dict[str, Any]:
        category = request.category or self.random_category()
        base_prompt = self.build_prompt(category, request.custom_parameters)
        llm_data = self.call_llm(base_prompt)
        code = llm_data.get("code", "")
        if not code:
            raise RuntimeError("The LLM response did not include any CAD code.")

        export_dir = GENERATED_DIR / category.replace("/", "_")
        export_dir.mkdir(parents=True, exist_ok=True)

        timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        safe_name = category.replace(" ", "_").replace("/", "_")
        output_path = export_dir / f"{safe_name}_{timestamp}.stl"

        cad_type = str(llm_data.get("cad_type", request.preferred_format or "openscad")).lower()
        if cad_type not in {"openscad", "cadquery"}:
            cad_type = "openscad"

        if not self.compile_generated_code(cad_type, code, output_path):
            fallback_code = self.create_openscad_fallback(category, request.custom_parameters)
            if not self.compile_openscad(fallback_code, output_path):
                raise RuntimeError("CAD compilation failed even with the fallback generator.")

        valid, reason = self.validate_mesh(output_path)
        if not valid:
            if output_path.exists():
                output_path.unlink(missing_ok=True)
            raise RuntimeError(reason)

        return {
            "category": category,
            "file_path": str(output_path),
            "title": llm_data.get("title", safe_name),
            "description": llm_data.get("description", "Generated STL model"),
            "notes": llm_data.get("notes", ""),
            "valid": True,
            "timestamp": datetime.utcnow().isoformat(),
        }
