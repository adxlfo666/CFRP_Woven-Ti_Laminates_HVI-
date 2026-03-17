"""
Instrucciones:
1. Ejecutar el script
2. Ingresar la familia de configuraciones deseada (ej: '9Ti/3CFRP', '9 3', o '9')
3. El programa genera automáticamente todos los archivos .k con las combinaciones

Formatos de entrada:
- '9Ti/3CFRP'  : 9 láminas de Titanio, 3 de CFRP
- '9T/3C'      : Formato abreviado
- '9 3'        : Solo números separados por espacio
- '9'          : Solo número de Ti (CFRP se calcula como 12 - Ti)

Configuración:
- ROOT_DIR: Ruta base donde se encuentra la plantilla y se guardarán los resultados
- TEMPLATE_NAME: Nombre del archivo plantilla .k
- PLY_COUNT: Número total de láminas (12)
- MID_CFRP: Material ID para CFRP (2)
- MID_TI: Material ID para Titanio (3)

Notas:
- Los contactos TIEBREAK entre láminas de Titanio se modifican automáticamente
- El glosario CSV registra todos los casos generados con su secuencia
"""

import os
import re
import csv
import math
import pathlib
from itertools import combinations
from typing import Tuple, List

# ============================================
# CONFIGURACIÓN
# ============================================
ROOT_DIR = r"C:\Users\Adolfo\Desktop\Adolfo\Combinatorias"
TEMPLATE_NAME = "HalfModel_12Ply_0.25mm_simplified.k"
TEMPLATE_K = os.path.join(ROOT_DIR, TEMPLATE_NAME)
OUTPUT_DIR = ROOT_DIR

pathlib.Path(OUTPUT_DIR).mkdir(parents=True, exist_ok=True)

PLY_COUNT = 12
MID_CFRP = 2
MID_TI = 3
MAP_MID = {'C': MID_CFRP, 'T': MID_TI}

TIEBREAK_BLOCK = """         9       1.0       1.0      -1.4       1.0       1.0       1.0       0.0
"""

INCLUDE_SEQUENCE_IN_FILENAME = True
PER_CASE_SUBFOLDERS = True
INCLUDE_SEQUENCE_IN_DIRNAME = True


def comb(n: int, k: int) -> int:
    return math.comb(n, k)


def parse_family_input(user_txt: str) -> Tuple[int, int] | None:
    s = user_txt.strip()
    if not s:
        return None
    m = re.match(r'^\s*(\d+)\s*(?:Ti|T)\s*\/\s*(\d+)\s*(?:CFRP|C)\s*$', s, flags=re.I)
    if m:
        return int(m.group(1)), int(m.group(2))
    parts = s.split()
    if len(parts) == 2 and parts[0].isdigit() and parts[1].isdigit():
        return int(parts[0]), int(parts[1])
    if len(parts) == 1 and parts[0].isdigit():
        nT = int(parts[0])
        nC = PLY_COUNT - nT
        return nT, nC
    return None


def generate_sequences(nT: int, nC: int, L: int = PLY_COUNT) -> List[str]:
    if nT < 0 or nC < 0 or nT + nC != L:
        raise ValueError("Conteos inválidos: nT + nC debe ser 12 y no negativos.")
    seqs = []
    for idxs in combinations(range(L), nT):
        arr = ['C'] * L
        for i in idxs:
            arr[i] = 'T'
        seqs.append(''.join(arr))
    return seqs


def load_template_lines(template_path: str) -> list[str]:
    if not os.path.exists(template_path):
        raise FileNotFoundError(f"No se encontró la plantilla: {template_path}")
    with open(template_path, 'r', encoding='utf-8', errors='ignore') as f:
        return f.readlines()


def index_ply_mid_lines(lines: list[str]) -> dict[int, int]:
    ply_mid_idx: dict[int, int] = {}
    i = 0
    N = len(lines)
    while i < N:
        line = lines[i]
        if line.strip().upper().startswith("*PART"):
            j = i + 1
            ply_num = None
            while j < min(N, i + 8):
                t = lines[j].strip()
                if t and not t.startswith("$"):
                    m = re.match(r"^Ply\s*(\d+)$", t, flags=re.I)
                    if m:
                        ply_num = int(m.group(1))
                        break
                j += 1
            if ply_num is not None and 1 <= ply_num <= PLY_COUNT:
                k = j + 1
                header_found = False
                while k < min(N, j + 12):
                    if "pid" in lines[k] and "mid" in lines[k] and lines[k].strip().startswith("$#"):
                        header_found = True
                        if k + 1 < N:
                            ply_mid_idx[ply_num] = k + 1
                        break
                    k += 1
                if not header_found:
                    k = j + 1
                    while k < min(N, j + 12):
                        toks = lines[k].strip().split()
                        if len(toks) >= 3 and all(re.match(r"^-?\d+(\.\d+)?$", tok) for tok in toks[:3]):
                            ply_mid_idx[ply_num] = k
                            break
                        k += 1
        i += 1
    return ply_mid_idx


def set_mid_on_line(original_line: str, mid_value: int) -> str:
    has_newline = original_line.endswith("\n")
    s = original_line[:-1] if has_newline else original_line

    spans = []
    in_tok = False
    start = None
    for i, ch in enumerate(s):
        if not ch.isspace() and not in_tok:
            in_tok = True
            start = i
        elif ch.isspace() and in_tok:
            in_tok = False
            spans.append((start, i))
    if in_tok:
        spans.append((start, len(s)))

    if len(spans) < 3:
        raise ValueError(f"Línea inesperada (no hay 3er campo 'mid'): {original_line!r}")

    a, b = spans[2]
    width = max(1, b - a)
    new_tok = str(mid_value).rjust(width)
    if len(new_tok) > width:
        new_tok = str(mid_value)

    new_line = s[:a] + new_tok + s[b:]
    return new_line + ("\n" if has_newline else "")


def index_contact_lines(lines: list[str]) -> dict[tuple[int, int], int]:
    contact_idx = {}
    i = 0
    N = len(lines)
    while i < N:
        line = lines[i]
        if "*CONTACT_AUTOMATIC_ONE_WAY_SURFACE_TO_SURFACE_TIEBREAK_ID" in line.upper():
            k = i + 2
            if k < N:
                title_line = lines[k].strip()
                match = re.match(r'^\s*\d+\s*(Delaminacion_B(\d+)_T(\d+))', title_line)
                if match:
                    interfaz = int(match.group(2)), int(match.group(3))
                    if interfaz[1] != interfaz[0] + 1:
                        i += 1
                        continue
                    param_line_idx = k + 8
                    if param_line_idx < N:
                        contact_idx[interfaz] = param_line_idx
        i += 1
    return contact_idx


def modify_contact_line_if_metallic(original_line: str, is_metallic: bool) -> str:
    if not is_metallic:
        return original_line
    return TIEBREAK_BLOCK


def apply_sequence_to_lines(base_lines: list[str], sequence: str, ply_mid_idx: dict[int, int], contact_idx: dict[tuple[int, int], int]) -> list[str]:
    out = list(base_lines)
    if len(sequence) != PLY_COUNT:
        raise ValueError("La secuencia debe tener longitud 12.")
    for pos, mat in enumerate(sequence, start=1):
        idx = ply_mid_idx.get(pos, None)
        if idx is None:
            continue
        mid_value = MAP_MID[mat]
        out[idx] = set_mid_on_line(out[idx], mid_value)

    for (n, n1), idx in contact_idx.items():
        if sequence[n - 1] == 'T' and sequence[n1 - 1] == 'T':
            out[idx] = modify_contact_line_if_metallic(out[idx], is_metallic=True)
    return out


def write_k(path: str, lines: list[str]) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w', encoding='utf-8', newline='') as f:
        f.writelines(lines)


def build_family_folder_name(nT: int, nC: int) -> str:
    return f"{nT}Ti_{nC}CFRP"


def build_case_folder_name(case_id: int, sequence: str, include_sequence: bool = INCLUDE_SEQUENCE_IN_DIRNAME) -> str:
    return f"case_{case_id:04d}_{sequence}" if include_sequence else f"case_{case_id:04d}"


def ensure_case_dir(family_dir: str, case_id: int, sequence: str) -> tuple[str, str]:
    folder_name = build_case_folder_name(case_id, sequence)
    case_dir = os.path.join(family_dir, folder_name)
    os.makedirs(case_dir, exist_ok=True)
    return case_dir, folder_name


def main():
    if not os.path.exists(TEMPLATE_K):
        print(f"Error: No se encontró la plantilla en {TEMPLATE_K}")
        return

    try:
        family_raw = input("Ingrese familia (ej: '9Ti/3CFRP', '9 3', o '9'): ").strip()
    except EOFError:
        family_raw = ""

    parsed = parse_family_input(family_raw)
    if not parsed:
        print("Entrada no reconocida. Usando 6Ti/6CFRP por defecto.")
        nT, nC = 6, 6
    else:
        nT, nC = parsed

    if nT + nC != PLY_COUNT or nT < 0 or nC < 0:
        print("Error: La familia debe sumar 12 láminas.")
        return

    family_folder = build_family_folder_name(nT, nC)
    family_dir = os.path.join(OUTPUT_DIR, family_folder)
    os.makedirs(family_dir, exist_ok=True)

    base_lines = load_template_lines(TEMPLATE_K)
    ply_mid_idx = index_ply_mid_lines(base_lines)
    contact_idx = index_contact_lines(base_lines)

    sequences = generate_sequences(nT, nC, L=PLY_COUNT)
    expected = comb(PLY_COUNT, nT)

    print(f"Casos a generar: {len(sequences)}")
    print("Iniciando procesamiento...")

    glossary_name = f"glossary_{family_folder}.csv"
    glossary_path = os.path.join(family_dir, glossary_name)
    
    with open(glossary_path, 'w', newline='', encoding='utf-8') as csvfile:
        writer = csv.writer(csvfile)
        writer.writerow(["case_id", "sequence", "n_Ti", "n_CFRP", "filename"])

        for i, seq in enumerate(sequences, start=1):
            if PER_CASE_SUBFOLDERS:
                case_dir, _ = ensure_case_dir(family_dir, i, seq)
            else:
                case_dir = family_dir

            if INCLUDE_SEQUENCE_IN_FILENAME:
                filename = f"case_{i:04d}_{seq}.k"
            else:
                filename = f"case_{i:04d}.k"

            out_path = os.path.join(case_dir, filename)

            out_lines = apply_sequence_to_lines(base_lines, seq, ply_mid_idx, contact_idx)
            write_k(out_path, out_lines)

            writer.writerow([i, seq, nT, nC, filename])

    print(f"Informacion guardada en {family_dir}")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"Error: {e}")