from pathlib import Path
from setuptools import setup
from setuptools.command.install import install
import shutil
import stat
import sys


class InstallGHConcat(install):
    """Instala ghconcat en ~/.bin/ghconcat y le da permisos de ejecución."""

    def run(self):
        super().run()

        src_file = Path(__file__).parent / "src" / "ghconcat.py"
        if not src_file.exists():
            print("No se encontró src/ghconcat.py", file=sys.stderr)
            sys.exit(1)

        dest_dir = Path.home() / ".bin"
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest_file = dest_dir / "ghconcat"

        shutil.copy2(src_file, dest_file)

        dest_file.chmod(dest_file.stat().st_mode | stat.S_IXUSR)

        print(f"✔ ghconcat instalado en {dest_file}")

        print(
            "\n⚠  Asegúrate de tener '~/.bin' incluido en tu PATH "
            "y de exportar la variable OPENAI_API_KEY en tu entorno."
        )


setup(
    name="ghconcat",
    version="1.0.0",
    description="Concatenador multi‑lenguaje con post‑procesado IA",
    author="GAHEOS",
    python_requires=">=3.8",
    packages=[],
    cmdclass={"install": InstallGHConcat},
)
