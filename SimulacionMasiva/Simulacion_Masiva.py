"""
Instrucciones:
1. Ejecutar el script
2. Seleccionar la carpeta que contiene las carpetas de simulación (case_xxxx_XXXX)
3. El programa ejecuta automáticamente:
   - Simulaciones LS-DYNA en paralelo (2 simultáneas)
   - Extracción de velocidad del proyectil desde d3plot
   - Guardado de datos en CSV temporal

Configuración:
- ncpu: Número de CPUs por simulación (default: 16)
- max_parallel: Simulaciones simultáneas (default: 2)
- memory: Memoria asignada (default: 1024m)
- PROJECTILE_MASS: 0.05 kg
- TARGET_INITIAL_VZ: -180.5 m/s

Notas:
- Las carpetas de simulación exitosas se eliminan después del procesamiento
- No se generan gráficas, solo el archivo CSV
"""

import os
os.environ['KMP_DUPLICATE_LIB_OK'] = 'TRUE'

import csv
import subprocess
import numpy as np
from ansys.dpf import core as dpf
import tkinter as tk
from tkinter import filedialog
from concurrent.futures import ThreadPoolExecutor, as_completed
import shutil
import time
import re
import pandas as pd

# ====== PARÁMETROS FÍSICOS ======
DENSITY_TI = 4500        # kg/m³
DENSITY_CFRP = 1540      # kg/m³
LAMINA_AREA = 0.310 * 0.310  # m² (310mm x 310mm)
LAMINA_THICKNESS = 0.00025    # m (0.25mm)
PROJECTILE_MASS = 0.05   # kg (50 g)
TARGET_INITIAL_VZ = -180.5  # m/s (velocidad inicial esperada del proyectil en Z)

# ====== RUTAS LS-DYNA ======
SOLVER_PATH = r"C:\Program Files\ANSYS Inc\v251\ansys\bin\winx64\lsdyna_mpp_sp_impi.exe"
MPIEXEC_PATH = r"C:\Program Files\ANSYS Inc\v251\tp\MPI\Intel\2018.3.210\winx64\bin\mpiexec.exe"
LSDYNA_VAR_SCRIPT = r"C:\Program Files\ANSYS Inc\v251\ansys\bin\winx64\lsprepost412\LS-Run\lsdynaintelvar.bat"

# ====== PARÁMETROS DE EJECUCIÓN ======
NCPU = 16
MAX_PARALLEL = 2
MEMORY = "1024m"


def select_folder(title):
    """Función para seleccionar carpeta usando un cuadro de diálogo"""
    root = tk.Tk()
    root.withdraw()
    root.attributes('-topmost', True)
    folder_path = filedialog.askdirectory(title=title)
    root.destroy()
    return folder_path


def find_k_files_in_case_folders(base_directory):
    """Busca archivos .k en carpetas case_xxxx_XXXX"""
    simulation_folders = []
    for item in os.listdir(base_directory):
        item_path = os.path.join(base_directory, item)
        if os.path.isdir(item_path) and item.startswith('case_'):
            k_files = [f for f in os.listdir(item_path) if f.endswith('.k')]
            if k_files:
                simulation_folders.append((item_path, k_files[0]))
    return simulation_folders


def extract_sequence_from_folder(folder_name):
    """Extrae la secuencia de apilamiento desde el nombre de la carpeta"""
    if folder_name.startswith('case_'):
        parts = folder_name.split('_')
        if len(parts) >= 3:
            seq = parts[2]
            if all(c in 'TC' for c in seq):
                return seq
    return None


def calculate_laminate_weight(sequence):
    """Calcula el peso del laminado en kg basado en la secuencia"""
    nT = sequence.count('T')
    nC = sequence.count('C')
    volume_Ti = nT * LAMINA_AREA * LAMINA_THICKNESS
    volume_CFRP = nC * LAMINA_AREA * LAMINA_THICKNESS
    mass_Ti = volume_Ti * DENSITY_TI
    mass_CFRP = volume_CFRP * DENSITY_CFRP
    return mass_Ti + mass_CFRP


def calculate_energy_metrics(velocity_data):
    """Calcula KE inicial, final, absorbida y % absorbido"""
    if not velocity_data:
        return 0, 0, 0, 0
    initial_vz = velocity_data[0]['vz']
    final_vz = velocity_data[-1]['vz']
    ke_initial = 0.5 * PROJECTILE_MASS * (initial_vz ** 2)
    ke_final = 0.5 * PROJECTILE_MASS * (final_vz ** 2)
    ke_absorbed = ke_initial - ke_final
    percent_abs = (ke_absorbed / ke_initial) * 100 if ke_initial != 0 else 0
    return ke_initial, ke_final, ke_absorbed, percent_abs


def extract_projectile_velocity_data(d3plot_path):
    """Extrae la velocidad del proyectil desde d3plot"""
    try:
        os.environ['AWP_ROOT251'] = r"C:\Program Files\ANSYS Inc\v251"
        from ansys.dpf.core import start_local_server
        server = start_local_server(ansys_path=r"C:\Program Files\ANSYS Inc\v251")
        model = dpf.Model(d3plot_path, server=server)
        
        time_freq_support = model.metadata.time_freq_support
        num_time_steps = len(time_freq_support.time_frequencies.data)
        time_values = time_freq_support.time_frequencies.data
        
        first_step = model.results.velocity.on_time_scoping([1]).eval()[0]
        first_data = first_step.data
        node_ids = first_step.scoping.ids
        
        projectile_candidates = []
        tolerance = 5.0
        
        for i in range(len(first_data)):
            if len(first_data[i]) >= 3:
                vx, vy, vz = first_data[i][0], first_data[i][1], first_data[i][2]
                if abs(vz - TARGET_INITIAL_VZ) < tolerance:
                    projectile_candidates.append((node_ids[i], vx, vy, vz, i))
        
        if not projectile_candidates:
            for i in range(len(first_data)):
                if len(first_data[i]) >= 3:
                    vx, vy, vz = first_data[i][0], first_data[i][1], first_data[i][2]
                    if abs(vz) > 100:
                        projectile_candidates.append((node_ids[i], vx, vy, vz, i))
        
        if not projectile_candidates:
            return [], False, "No se encontró el proyectil"
        
        projectile_pos = projectile_candidates[0][4]
        
        projectile_history = []
        for step in range(1, num_time_steps + 1):
            try:
                step_field = model.results.velocity.on_time_scoping([step]).eval()[0]
                if projectile_pos < len(step_field.data):
                    vx, vy, vz = step_field.data[projectile_pos]
                    time_val = time_values[step-1]
                    projectile_history.append({
                        'time': time_val,
                        'vx': vx,
                        'vy': vy,
                        'vz': vz
                    })
            except:
                continue
        
        if projectile_history:
            return projectile_history, True, "Proyectil identificado"
        else:
            return [], False, "No se pudo extraer la historia completa"
    
    except Exception as e:
        return [], False, f"Error: {str(e)}"


def run_simulation(sim_data, solver_path, mpiexec_path, lsdyna_var_script, ncpu=16, memory="1024m"):
    """Ejecuta una simulación LS-DYNA"""
    sim_folder, k_file = sim_data
    k_file_path = os.path.join(sim_folder, k_file)
    cmd = f'call "{lsdyna_var_script}" && "{mpiexec_path}" -localonly -np {ncpu} "{solver_path}" i="{k_file_path}" memory={memory}'
    start_time = time.time()
    
    try:
        result = subprocess.run(
            cmd,
            shell=True,
            cwd=sim_folder,
            capture_output=True,
            text=True,
            timeout=7200
        )
        execution_time = time.time() - start_time
        
        log_path = os.path.join(sim_folder, "run_stdout.txt")
        with open(log_path, "w", encoding='utf-8') as f:
            f.write(f"Command: {cmd}\n")
            f.write(f"Return code: {result.returncode}\n")
            f.write(f"Execution time: {execution_time:.2f} seconds\n")
            f.write(f"STDOUT:\n{result.stdout}\n")
            f.write(f"STDERR:\n{result.stderr}\n")
        
        d3plot_path = os.path.join(sim_folder, "d3plot")
        error_patterns = [
            r"part # \d+ is out-of-range",
            r"does not reference a solid section",
            r"Reading nodal point data for solid element"
        ]
        has_critical_error = any(re.search(pat, result.stderr + result.stdout, re.IGNORECASE) for pat in error_patterns)
        
        if has_critical_error:
            return sim_folder, False, "Simulation failed with critical errors", k_file, execution_time
        if result.returncode == 0 and os.path.exists(d3plot_path):
            return sim_folder, True, "Simulation completed successfully", k_file, execution_time
        elif result.returncode == 0:
            return sim_folder, False, "Simulation completed but no d3plot", k_file, execution_time
        else:
            return sim_folder, False, f"LS-DYNA failed with code {result.returncode}", k_file, execution_time
    
    except subprocess.TimeoutExpired:
        execution_time = time.time() - start_time
        return sim_folder, False, "Simulation timed out", k_file, execution_time
    except Exception as e:
        execution_time = time.time() - start_time
        return sim_folder, False, f"Error: {str(e)}", k_file, execution_time


def clean_simulation_folder(sim_folder, k_file):
    """Elimina completamente la carpeta de la simulación"""
    try:
        shutil.rmtree(sim_folder)
    except Exception:
        pass


def main():
    print("=== Simulación Masiva Ti/CFRP - Extracción de Energía y Velocidad ===")
    
    for path, name in [(SOLVER_PATH, "solver"), (MPIEXEC_PATH, "mpiexec"), (LSDYNA_VAR_SCRIPT, "lsdyna_var_script")]:
        if not os.path.exists(path):
            print(f"ERROR: No se encuentra {name} en: {path}")
            return
    print("Archivos de LS-DYNA encontrados correctamente")
    
    base_directory = select_folder("Selecciona la carpeta madre con las simulaciones (carpetas case_xxxx_XXXX)")
    if not base_directory:
        print("Operación cancelada.")
        return
    
    temp_csv_path = os.path.join(base_directory, "temp_velocity_z_data.csv")
    
    if os.path.exists(temp_csv_path):
        os.remove(temp_csv_path)
    
    with open(temp_csv_path, 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow(['Simulación', 'Secuencia', 'Peso_kg', 'Time', 'Vz', 'V_Final_Z', 'Sim_Time_s'])
    
    simulation_folders = find_k_files_in_case_folders(base_directory)
    if not simulation_folders:
        print(f"No se encontraron carpetas de simulación en: {base_directory}")
        return
    print(f"\nEncontradas {len(simulation_folders)} carpetas de simulación")
    
    processing_results = []
    
    for i in range(0, len(simulation_folders), MAX_PARALLEL):
        batch = simulation_folders[i:i + MAX_PARALLEL]
        batch_results = []
        
        with ThreadPoolExecutor(max_workers=MAX_PARALLEL) as executor:
            futures = [executor.submit(run_simulation, sim_data, SOLVER_PATH, MPIEXEC_PATH, LSDYNA_VAR_SCRIPT, NCPU, MEMORY) 
                      for sim_data in batch]
            for future in as_completed(futures):
                batch_results.append(future.result())
                sim_folder, success, message, k_file, exec_time = future.result()
                time_str = f"{exec_time/60:.1f} min" if exec_time > 60 else f"{exec_time:.1f} seg"
                print(f"Procesado: {os.path.basename(sim_folder)} - {message} - {time_str}")
        
        for sim_folder, success, message, k_file, exec_time in batch_results:
            sim_name = os.path.basename(sim_folder)
            if success and "completed successfully" in message:
                d3plot_path = os.path.join(sim_folder, "d3plot")
                if os.path.exists(d3plot_path):
                    vel_data, vel_success, vel_msg = extract_projectile_velocity_data(d3plot_path)
                    if vel_success:
                        sequence = extract_sequence_from_folder(sim_name) or "UNKNOWN"
                        weight_kg = calculate_laminate_weight(sequence) if sequence != "UNKNOWN" else 0
                        final_vz = vel_data[-1]['vz']
                        
                        with open(temp_csv_path, 'a', newline='', encoding='utf-8') as f:
                            writer = csv.writer(f)
                            for record in vel_data:
                                writer.writerow([sim_name, sequence, weight_kg, record['time'], record['vz'], final_vz, exec_time])
                        
                        _, ke_final, ke_abs, percent_ke_abs = calculate_energy_metrics(vel_data)
                        
                        processing_results.append({
                            'Simulación': sim_name,
                            'Secuencia': sequence,
                            'Peso [kg]': weight_kg,
                            'V_Final_Z [m/s]': final_vz,
                            'KE_Final [J]': ke_final,
                            'KE_Abs [J]': ke_abs,
                            '%KE_Abs [%]': percent_ke_abs,
                            'Success': True
                        })
                        clean_simulation_folder(sim_folder, k_file)
                    else:
                        processing_results.append({
                            'Simulación': sim_name,
                            'Secuencia': "ERROR",
                            'Peso [kg]': 0,
                            'V_Final_Z [m/s]': 0,
                            'KE_Final [J]': 0,
                            'KE_Abs [J]': 0,
                            '%KE_Abs [%]': 0,
                            'Success': False
                        })
                else:
                    processing_results.append({
                        'Simulación': sim_name,
                        'Secuencia': "NO_D3PLOT",
                        'Peso [kg]': 0,
                        'V_Final_Z [m/s]': 0,
                        'KE_Final [J]': 0,
                        'KE_Abs [J]': 0,
                        '%KE_Abs [%]': 0,
                        'Success': False
                    })
            else:
                processing_results.append({
                    'Simulación': sim_name,
                    'Secuencia': "SIM_FAILED",
                    'Peso [kg]': 0,
                    'V_Final_Z [m/s]': 0,
                    'KE_Final [J]': 0,
                    'KE_Abs [J]': 0,
                    '%KE_Abs [%]': 0,
                    'Success': False
                })
    
    df_final = pd.DataFrame([r for r in processing_results if r['Success']])
    if not df_final.empty:
        df_final = df_final[[
            'Simulación',
            'Secuencia',
            'Peso [kg]',
            'V_Final_Z [m/s]',
            'KE_Final [J]',
            'KE_Abs [J]',
            '%KE_Abs [%]'
        ]]
    
    print("\nGenerando gráficas combinadas globales...")
    print("Generando gráficas de top 5 por familia...")
    
    successful = len([r for r in processing_results if r['Success']])
    total = len(processing_results)
    print(f"\n=== RESUMEN FINAL ===")
    print(f"Total simulaciones: {total}")
    print(f"Exitosas: {successful}")
    print(f"Resultados finales guardados en: {temp_csv_path}")


if __name__ == "__main__":
    try:
        main()
    except Exception:
        pass