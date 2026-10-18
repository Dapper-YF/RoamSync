"""Process-local evaluation overlays, never edits the serving app."""
import importlib.util
from pathlib import Path
import runpy
import sys

directory = Path(sys.argv.pop(1))
for name in ("candidate_decisions", "planning_goals", "openai_planner"):
    spec = importlib.util.spec_from_file_location("app." + name, directory / (name + ".py"))
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
runpy.run_path(str(directory / "run_bounded_decision_eval.py"), run_name="__main__")
