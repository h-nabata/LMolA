from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from lmola.schemas import MoleculeBuildRequest, ToolCallRecord, ToolResult


def _record(status: str, run_dir: Path, message: str = "", stderr: str = "") -> ToolCallRecord:
    return ToolCallRecord(
        timestamp=datetime.now(timezone.utc).isoformat(),
        tool="rdkit",
        command=[],
        cwd=str(run_dir),
        returncode=None,
        stdout_excerpt=message[:2000],
        stderr_excerpt=stderr[:2000],
        status=status,
    )


def _write_xyz(mol, conf_id: int, xyz_path: Path) -> None:
    conf = mol.GetConformer(conf_id)
    atoms = mol.GetAtoms()
    lines = [str(len(atoms)), "LMolA RDKit-generated structure"]
    for atom in atoms:
        pos = conf.GetAtomPosition(atom.GetIdx())
        lines.append(f"{atom.GetSymbol()} {pos.x:.8f} {pos.y:.8f} {pos.z:.8f}")
    xyz_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def run_rdkit_generation(req: MoleculeBuildRequest, run_dir: Path) -> ToolResult:
    try:
        from rdkit import Chem
        from rdkit.Chem import AllChem
    except Exception:
        msg = "RDKit is unavailable. Install LMolA with the rdkit extra or install RDKit in the environment."
        return ToolResult(status="error", message=msg, cwd=str(run_dir), tool_calls=[_record("error", run_dir, msg)])

    smiles = (req.smiles or "").strip()
    if not smiles:
        msg = "SMILES input is required for small_molecule RDKit generation."
        return ToolResult(status="error", message=msg, cwd=str(run_dir), tool_calls=[_record("error", run_dir, msg)])

    mol = Chem.MolFromSmiles(smiles)
    if mol is None:
        msg = f"Invalid SMILES string: {smiles}"
        return ToolResult(status="error", message=msg, cwd=str(run_dir), tool_calls=[_record("error", run_dir, msg)])

    opts = req.build_options
    if opts.add_hydrogens:
        mol = Chem.AddHs(mol)

    params = AllChem.ETKDGv3() if hasattr(AllChem, "ETKDGv3") and opts.embed_method.upper() == "ETKDGV3" else AllChem.ETKDG()
    if opts.random_seed is not None:
        params.randomSeed = int(opts.random_seed)

    conf_id = AllChem.EmbedMolecule(mol, params)
    if conf_id < 0:
        msg = "RDKit failed to embed a 3D conformer for the provided SMILES."
        return ToolResult(status="error", message=msg, cwd=str(run_dir), tool_calls=[_record("error", run_dir, msg)])

    optimize = (opts.optimize or "").lower()
    if optimize == "uff":
        try:
            AllChem.UFFOptimizeMolecule(mol, confId=conf_id)
        except Exception:
            pass
    elif optimize == "mmff":
        try:
            props = AllChem.MMFFGetMoleculeProperties(mol)
            if props is not None:
                AllChem.MMFFOptimizeMolecule(mol, mmffVariant="MMFF94", confId=conf_id)
        except Exception:
            pass

    generated=[]
    xyz_path = run_dir / "molecule.xyz"
    _write_xyz(mol, conf_id, xyz_path)
    generated.append("molecule.xyz")

    if any(fmt.lower() == "sdf" for fmt in opts.output_formats):
        sdf_path = run_dir / "molecule.sdf"
        writer = Chem.SDWriter(str(sdf_path))
        writer.write(mol, conf_id)
        writer.close()
        generated.append("molecule.sdf")

    msg = "RDKit generation completed"
    return ToolResult(status="ok", message=msg, cwd=str(run_dir), generated_files=generated, tool_calls=[_record("ok", run_dir, msg)])
