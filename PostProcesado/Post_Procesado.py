"""
Instrucciones:
1. Ejecutar el script
2. Seleccionar el archivo CSV original de resultados de simulación
3. El programa genera automáticamente:
   - Archivos CSV procesados y ordenados
   - Histograma de distribución de velocidad residual
   - Boxplot de velocidad vs posición de Titanio
   - Gráficas Top 10 por familia de configuración

Notas:
- Las velocidades se invierten (signo cambiado) para interpretación física
- La familia se determina contando 'T' (Titanio) y 'C' (CFRP) en la secuencia
================================================================================
"""

import os
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import re
import tkinter as tk
from tkinter import filedialog

plt.ioff()

# ===== Parámetros físicos =====
PROJECTILE_MASS = 0.05

# ===== Parámetros para histograma =====
HIST_XMIN = -40
HIST_XMAX = 180
HIST_BIN_WIDTH = 20
HIST_X_MARGIN = 5


def select_csv_file():
    """Abre ventana para seleccionar el archivo CSV original"""
    root = tk.Tk()
    root.withdraw()
    root.attributes('-topmost', True)
    
    csv_path = filedialog.askopenfilename(
        title="Selecciona el archivo CSV original de resultados",
        filetypes=[("Archivos CSV", "*.csv"), ("Todos los archivos", "*.*")]
    )
    
    root.destroy()
    return csv_path


def extract_case_number(sim_name):
    """Extrae el número de caso del nombre de simulación"""
    match = re.search(r'case_(\d+)_', str(sim_name))
    return int(match.group(1)) if match else 999999


def get_family_from_sequence(seq):
    """Obtiene la familia basada en la secuencia de capas"""
    if not seq or not all(c in 'TC' for c in str(seq)):
        return "UNKNOWN"
    nT = str(seq).count('T')
    nC = str(seq).count('C')
    return f"{nT}Ti_{nC}CFRP"


def plot_histogram(df_final, output_dir):
    """Genera histograma de distribución de velocidad final"""
    if 'V_Final_Z [m/s]' not in df_final.columns:
        return
    
    data = df_final['V_Final_Z [m/s]'].dropna()
    if len(data) == 0:
        return
    
    bins = np.arange(HIST_XMIN, HIST_XMAX + HIST_BIN_WIDTH, HIST_BIN_WIDTH)
    
    fig, ax = plt.subplots(figsize=(12, 7))
    counts, edges, patches = ax.hist(data, bins=bins, edgecolor='black', rwidth=0.92, color='steelblue')
    
    ax.set_xlim(HIST_XMIN - HIST_X_MARGIN, HIST_XMAX)
    ax.set_xticks(bins)
    
    ax.set_title('Distribución de velocidad residual final', fontsize=15, pad=20)
    ax.set_xlabel("Velocidad residual final en Z [m/s]", fontsize=12)
    ax.set_ylabel("Número de simulaciones", fontsize=12)
    
    for count, left, right in zip(counts, edges[:-1], edges[1:]):
        if count > 0:
            ax.text((left + right) / 2, count + 0.15, f"{int(count)}",
                    ha='center', va='bottom', fontsize=11)
    
    plt.tight_layout()
    plt.savefig(os.path.join(output_dir, "histograma_distribucion.png"), dpi=300, bbox_inches='tight')
    plt.close()


def plot_boxplot_by_position(df_final, output_graphs_dir, base_dir, nombre_base):
    """Genera boxplot de velocidad residual vs posición del Ti"""
    if 'Secuencia' not in df_final.columns or 'V_Final_Z [m/s]' not in df_final.columns:
        return
    
    secuencias = df_final['Secuencia'].astype(str)
    longitudes = secuencias.str.len()
    
    if longitudes.nunique() != 1:
        return
    
    n_capas = longitudes.iloc[0]
    datos_por_posicion = {i: [] for i in range(1, n_capas + 1)}
    
    for idx, fila in df_final.iterrows():
        secuencia = str(fila['Secuencia'])
        velocidad = fila['V_Final_Z [m/s]']
        
        for pos in range(len(secuencia)):
            if secuencia[pos] == 'T':
                datos_por_posicion[pos + 1].append(velocidad)
    
    posiciones = sorted(datos_por_posicion.keys())
    datos_para_grafica = [datos_por_posicion[pos] for pos in posiciones]
    
    fig, ax = plt.subplots(figsize=(12, 7))
    
    bp = ax.boxplot(datos_para_grafica, 
                    positions=posiciones, 
                    widths=0.6,
                    patch_artist=True,
                    showfliers=False,
                    boxprops=dict(facecolor='white', edgecolor='black', linewidth=1.5),
                    medianprops=dict(color='orange', linewidth=2.5),
                    whiskerprops=dict(color='black', linewidth=1.5),
                    capprops=dict(color='black', linewidth=1.5))
    
    ax.set_xlabel('Posición del titanio en el laminado', fontsize=12)
    ax.set_ylabel('Velocidad residual final [m/s]', fontsize=12)
    ax.set_title('Distribución de velocidad residual según posición del Ti', 
             fontsize=14, pad=20)
    
    ax.set_xticks(posiciones)
    ax.set_xticklabels([str(p) for p in posiciones], fontsize=10)
    ax.grid(True, axis='y', linestyle='', alpha=0.7, linewidth=0.5)
    
    plt.tight_layout()
    
    archivo_png = os.path.join(output_graphs_dir, f"{nombre_base}_boxplot.png")
    plt.savefig(archivo_png, dpi=300, bbox_inches='tight')
    plt.close(fig)
    
    estadisticos = []
    for pos in posiciones:
        datos = np.array(datos_por_posicion[pos])
        if len(datos) > 0:
            estadisticos.append({
                'Posicion': pos,
                'N_casos': len(datos),
                'Mediana': round(np.percentile(datos, 50), 4),
                'Q1': round(np.percentile(datos, 25), 4),
                'Q3': round(np.percentile(datos, 75), 4),
                'IQR': round(np.percentile(datos, 75) - np.percentile(datos, 25), 4),
                'Min': round(np.min(datos), 4),
                'Max': round(np.max(datos), 4),
                'Media': round(np.mean(datos), 4),
                'Std': round(np.std(datos), 4)
            })
    
    df_stats = pd.DataFrame(estadisticos)
    archivo_stats = os.path.join(base_dir, f"{nombre_base}_estadisticos.csv")
    df_stats.to_csv(archivo_stats, index=False)


def process_simulation_data(csv_path):
    """Procesa todos los datos y genera archivos y gráficas"""
    
    base_dir = os.path.dirname(os.path.abspath(csv_path))
    output_graphs_dir = os.path.join(base_dir, "postprocessing_graphs")
    os.makedirs(output_graphs_dir, exist_ok=True)
    
    base_name = os.path.splitext(os.path.basename(csv_path))[0]
    
    final_csv_path = os.path.join(base_dir, f"{base_name}_final.csv")
    ordered_by_case_path = os.path.join(base_dir, f"{base_name}_ordenado_por_caso.csv")
    ordered_by_velocity_path = os.path.join(base_dir, f"{base_name}_ordenado_por_velocidad.csv")
    ordered_by_energy_path = os.path.join(base_dir, f"{base_name}_ordenado_por_absorcion.csv")
    
    df_temp = pd.read_csv(csv_path, header=0, names=['Simulación', 'Secuencia', 'Peso_kg', 'Time', 'Vz'])
    df_temp['Time'] = pd.to_numeric(df_temp['Time'], errors='coerce')
    df_temp['Vz'] = pd.to_numeric(df_temp['Vz'], errors='coerce')
    df_temp = df_temp.dropna(subset=['Time', 'Vz'])
    
    df_temp['Vz'] = -df_temp['Vz']
    
    if 'Simulación' not in df_temp.columns:
        return
    
    results = []
    for sim_name in df_temp['Simulación'].unique():
        sim_data = df_temp[df_temp['Simulación'] == sim_name].sort_values('Time')
        if sim_data.empty:
            continue
        
        initial_vz = sim_data['Vz'].iloc[0]
        final_vz = sim_data['Vz'].iloc[-1]
        
        ke_initial = 0.5 * PROJECTILE_MASS * (initial_vz ** 2)
        ke_final = 0.5 * PROJECTILE_MASS * (final_vz ** 2)
        ke_abs = ke_initial - ke_final
        percent_abs = (ke_abs / ke_initial) * 100 if ke_initial != 0 else 0
        
        seq = sim_data['Secuencia'].iloc[0]
        weight_kg = sim_data['Peso_kg'].iloc[0]
        
        results.append({
            'Simulación': sim_name,
            'Secuencia': seq,
            'Peso [kg]': weight_kg,
            'V_Inicial_Z [m/s]': initial_vz,
            'V_Final_Z [m/s]': final_vz,
            'KE_Inicial [J]': ke_initial,
            'KE_Final [J]': ke_final,
            'KE_Abs [J]': ke_abs,
            '%KE_Abs [%]': percent_abs
        })
    
    df_final = pd.DataFrame(results)
    df_final.to_csv(final_csv_path, index=False, encoding='utf-8')
    
    df_final['case_num'] = df_final['Simulación'].apply(extract_case_number)
    df_ordered_case = df_final.sort_values('case_num').drop(columns=['case_num'])
    df_ordered_case.to_csv(ordered_by_case_path, index=False, encoding='utf-8')
    
    df_ordered_velocity = df_final.sort_values('V_Final_Z [m/s]', ascending=False)
    df_ordered_velocity.to_csv(ordered_by_velocity_path, index=False, encoding='utf-8')
    
    df_ordered_energy = df_final.sort_values('%KE_Abs [%]', ascending=False)
    df_ordered_energy.to_csv(ordered_by_energy_path, index=False, encoding='utf-8')
    
    if not df_final.empty:
        df_final['Familia'] = df_final['Secuencia'].apply(get_family_from_sequence)
        
        for familia in df_final['Familia'].unique():
            family_df = df_final[df_final['Familia'] == familia]
            top10 = family_df.nlargest(10, '%KE_Abs [%]')
            if top10.empty:
                continue
            
            plt.figure(figsize=(14, 10))
            for _, row in top10.iterrows():
                sim = row['Simulación']
                data = df_temp[df_temp['Simulación'] == sim].sort_values('Time')
                label = f"{sim} ({row['%KE_Abs [%]']:.1f}%)"
                plt.plot(data['Time'], data['Vz'], linewidth=2, label=label)
            plt.xlabel('Tiempo (s)')
            plt.ylabel('Velocidad Z [m/s]', fontsize=10)
            plt.title(f'Top 10 - Velocidad Z: {familia}')
            plt.grid(True, alpha=0.3)
            plt.legend(loc='best', fontsize='medium')
            plt.tight_layout()
            plt.savefig(os.path.join(output_graphs_dir, f"top10_velocity_{familia}.png"), dpi=300, bbox_inches='tight')
            plt.close()
            
            plt.figure(figsize=(14, 10))
            for _, row in top10.iterrows():
                sim = row['Simulación']
                data = df_temp[df_temp['Simulación'] == sim].sort_values('Time')
                initial_vz = data['Vz'].iloc[0]
                ke_initial = 0.5 * PROJECTILE_MASS * (initial_vz ** 2)
                ke_abs = ke_initial - 0.5 * PROJECTILE_MASS * (data['Vz'] ** 2)
                label = f"{sim} ({row['%KE_Abs [%]']:.1f}%)"
                plt.plot(data['Time'], ke_abs, linewidth=2, label=label)
            plt.xlabel('Tiempo (s)')
            plt.ylabel('Energía Absorbida (J)')
            plt.title(f'Top 10 - Energía Absorbida: {familia}')
            plt.grid(True, alpha=0.3)
            plt.legend(loc='best', fontsize='medium')
            plt.tight_layout()
            plt.savefig(os.path.join(output_graphs_dir, f"top10_energy_{familia}.png"), dpi=300, bbox_inches='tight')
            plt.close()
    
    plot_histogram(df_final, output_graphs_dir)
    plot_boxplot_by_position(df_final, output_graphs_dir, base_dir, base_name)
    
    print(f"Informacion guardada en {base_dir}")


if __name__ == "__main__":
    print("Iniciando procesamiento...")
    
    csv_path = select_csv_file()
    
    if csv_path:
        try:
            process_simulation_data(csv_path)
        except Exception:
            pass