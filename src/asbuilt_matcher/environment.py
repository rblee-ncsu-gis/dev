"""Inspect installed capabilities without installing or checking out extensions."""

import importlib
import importlib.metadata
import platform
import shutil
import sys

PACKAGES = {
    "pymupdf": "PyMuPDF", "numpy": "numpy", "cv2": "opencv-python",
    "scipy": "scipy", "shapely": "shapely", "networkx": "networkx",
    "torch": "torch", "torchvision": "torchvision", "arcpy": None,
}


def check_environment():
    report = {
        "python": sys.version, "executable": sys.executable,
        "prefix": sys.prefix, "platform": platform.platform(),
        "packages": {}, "tesseract_path": shutil.which("tesseract"),
    }
    for module_name, distribution in PACKAGES.items():
        entry = {"status": "error", "version": None}
        try:
            if distribution:
                try:
                    entry["version"] = importlib.metadata.version(distribution)
                except importlib.metadata.PackageNotFoundError:
                    pass
            module = importlib.import_module(module_name)
            entry.update(status="ok", module_path=getattr(module, "__file__", None))
            entry["version"] = entry["version"] or getattr(module, "__version__", None)
            if module_name == "torch":
                available = module.cuda.is_available()
                entry["cuda"] = {
                    "available": available, "build_version": module.version.cuda,
                    "devices": [module.cuda.get_device_name(i)
                                for i in range(module.cuda.device_count())] if available else [],
                }
            if module_name == "arcpy":
                entry["install"] = module.GetInstallInfo()
                entry["product"] = module.ProductInfo()
                entry["extensions"] = {}
                for extension in ("Spatial", "ImageAnalyst"):
                    try:
                        entry["extensions"][extension] = module.CheckExtension(extension)
                    except Exception as exc:
                        entry["extensions"][extension] = {"error": str(exc)}
        except Exception as exc:
            entry.update(status="error", error=f"{type(exc).__name__}: {exc}")
        report["packages"][module_name] = entry
    report["pdf_ready"] = report["packages"]["pymupdf"]["status"] == "ok"
    return report
