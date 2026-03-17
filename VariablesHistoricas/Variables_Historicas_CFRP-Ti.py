"""
Instrucciones:
1. Ejecutar el script 
2. Seleccionar la carpeta que contiene los casos (case_001, case_002, etc.)
3. El programa ejecuta automáticamente ambos análisis (CFRP y Titanio)

Outputs:
- RESULTS_CFRP_Damage/     : Gráficas y Excel para análisis CFRP
- RESULTS_TITANIUM_Damage/ : Gráficas y Excel para análisis Titanio

Ojo:
- PART_RANGES: Rangos de Element IDs por parte (ajustar según modelo)

================================================================================
"""

import os
import sys
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from ansys.dpf import core as dpf
from ansys.dpf.core import start_local_server
import warnings
import tkinter as tk
from tkinter import filedialog

warnings.filterwarnings('ignore')
plt.ioff()

# ============================================
# CONFIGURACIÓN
# ============================================
os.environ['KMP_DUPLICATE_LIB_OK'] = 'TRUE'
os.environ['AWP_ROOT251'] = r"C:\Program Files\ANSYS Inc\v251"
ANSYS_PATH = r"C:\Program Files\ANSYS Inc\v251"

PART_RANGES = {
    1:  (48051,   96100),
    2:  (144151,  192200),
    3:  (240251,  288300),
    4:  (336351,  384400),
    5:  (432451,  480500),
    6:  (528551,  576600),
    7:  (624651,  672700),
    8:  (720751,  768800),
    9:  (816851,  864900),
    10: (912951,  961000),
    11: (1009051, 1057100),
    12: (1105151, 1153200),
    13: (1154451, 2028200)
}


def seleccionar_carpeta(titulo="Seleccionar carpeta"):
    """Abre ventana para seleccionar carpeta."""
    root = tk.Tk()
    root.withdraw()
    root.attributes('-topmost', True)
    carpeta = filedialog.askdirectory(title=titulo, mustexist=True)
    root.destroy()
    return carpeta if carpeta else None


def get_part_ids(case_name, material_type='C'):
    """Parsea el nombre del caso para identificar partes."""
    if '_' not in case_name:
        return list(range(1, 13))
    
    sequence = case_name.split('_')[-1].upper()
    part_ids = []
    
    for idx, char in enumerate(sequence[:12], start=1):
        if char == material_type:
            part_ids.append(idx)
    
    return part_ids


def get_fields_from_container(hist_result):
    """Extrae lista de fields desde un FieldsContainer."""
    fields_list = []
    
    try:
        if hasattr(hist_result, '_fields') and hist_result._fields is not None:
            fields_list = list(hist_result._fields)
            return fields_list
        
        if hasattr(hist_result, 'get_field_by_time_id'):
            try:
                field = hist_result.get_field_by_time_id(1)
                if field is not None:
                    fields_list = [field]
                    return fields_list
            except:
                pass
        
        if hasattr(hist_result, '__iter__'):
            try:
                for field in hist_result:
                    fields_list.append(field)
                if len(fields_list) > 0:
                    return fields_list
            except:
                pass
        
        if hasattr(hist_result, 'fields'):
            fields_obj = hist_result.fields
            if hasattr(fields_obj, '__iter__'):
                fields_list = list(fields_obj)
                return fields_list
    except:
        pass
    
    return fields_list


def find_d3plot(case_folder):
    """Busca archivo d3plot en la carpeta del caso."""
    for root, dirs, files in os.walk(case_folder):
        for f in files:
            if f.startswith('d3plot') and len(f) <= 7:
                return os.path.join(root, f)
    return None


def extract_cfrp_damage_history(d3plot_path, cfrp_part_ids):
    """Extrae evolución de daño para partes CFRP."""
    try:
        server = start_local_server(ansys_path=ANSYS_PATH)
        model = dpf.Model(d3plot_path, server=server)
        
        time_freq = model.metadata.time_freq_support
        num_steps = len(time_freq.time_frequencies.data)
        if num_steps == 0:
            server.shutdown()
            return [], 0
        
        hist_var = 'history_variablesihv__[1__5]'
        if hist_var not in dir(model.results):
            server.shutdown()
            return [], 0
        
        mesh = model.metadata.meshed_region
        all_elem_ids = set([elem.id for elem in mesh.elements])
        
        cfrp_elements = []
        for pid in cfrp_part_ids:
            if pid in PART_RANGES:
                min_eid, max_eid = PART_RANGES[pid]
                part_elems = [eid for eid in all_elem_ids if min_eid <= eid <= max_eid]
                cfrp_elements.extend(part_elems)
        
        total_cfrp = len(cfrp_elements)
        damage_history = []
        
        for itime in range(1, num_steps + 1):
            try:
                result_obj = getattr(model.results, hist_var)
                hist_result = result_obj.on_time_scoping([itime]).eval()
                fields_list = get_fields_from_container(hist_result)
                
                if len(fields_list) == 0:
                    continue
                
                time_val = time_freq.time_frequencies.data[itime-1]
                entry = {'time_step': itime, 'time_value': time_val}
                
                for i in range(min(5, len(fields_list))):
                    try:
                        field_data = fields_list[i]
                        
                        if hasattr(field_data, 'data') and field_data.data is not None:
                            data_array = field_data.data
                            scoping = getattr(field_data, 'scoping', None)
                            
                            if scoping is not None:
                                scoping_map = {eid: idx for idx, eid in enumerate(scoping)}
                            else:
                                scoping_map = None
                            
                            cfrp_vals = []
                            for eid in cfrp_elements:
                                val = 1.0
                                if scoping_map is not None and eid in scoping_map:
                                    idx = scoping_map[eid]
                                    if idx < len(data_array):
                                        val = float(data_array[idx])
                                cfrp_vals.append(val)
                            
                            if len(cfrp_vals) > 0:
                                failed = max(0, total_cfrp - np.sum(cfrp_vals))
                                entry[f'Damage_{i+1}'] = float(failed)
                            else:
                                entry[f'Damage_{i+1}'] = 0.0
                        else:
                            entry[f'Damage_{i+1}'] = 0.0
                    except:
                        entry[f'Damage_{i+1}'] = 0.0
                
                damage_history.append(entry)
            except:
                continue
        
        server.shutdown()
        return damage_history, total_cfrp
        
    except:
        if 'server' in locals():
            server.shutdown()
        return [], 0


def extract_titanium_history(d3plot_path, titanium_part_ids):
    """Extrae variables históricas (2-5) para partes de Titanio."""
    try:
        server = start_local_server(ansys_path=ANSYS_PATH)
        model = dpf.Model(d3plot_path, server=server)
        
        time_freq = model.metadata.time_freq_support
        num_steps = len(time_freq.time_frequencies.data)
        if num_steps == 0:
            server.shutdown()
            return [], 0
        
        hist_var = 'history_variablesihv__[1__5]'
        if hist_var not in dir(model.results):
            server.shutdown()
            return [], 0
        
        mesh = model.metadata.meshed_region
        all_elem_ids = set([elem.id for elem in mesh.elements])
        
        titanium_elements = []
        for pid in titanium_part_ids:
            if pid in PART_RANGES:
                min_eid, max_eid = PART_RANGES[pid]
                part_elems = [eid for eid in all_elem_ids if min_eid <= eid <= max_eid]
                titanium_elements.extend(part_elems)
        
        total_titanium = len(titanium_elements)
        history_data = []
        
        for itime in range(1, num_steps + 1):
            try:
                result_obj = getattr(model.results, hist_var)
                hist_result = result_obj.on_time_scoping([itime]).eval()
                fields_list = get_fields_from_container(hist_result)
                
                if len(fields_list) == 0:
                    continue
                
                time_val = time_freq.time_frequencies.data[itime-1]
                entry = {'time_step': itime, 'time_value': time_val}
                
                for i in range(1, min(5, len(fields_list))):
                    try:
                        field_data = fields_list[i]
                        
                        if hasattr(field_data, 'data') and field_data.data is not None:
                            data_array = field_data.data
                            scoping = getattr(field_data, 'scoping', None)
                            
                            if scoping is not None:
                                scoping_map = {eid: idx for idx, eid in enumerate(scoping)}
                            else:
                                scoping_map = None
                            
                            titanium_vals = []
                            for eid in titanium_elements:
                                val = 0.0
                                if scoping_map is not None and eid in scoping_map:
                                    idx = scoping_map[eid]
                                    if idx < len(data_array):
                                        val = float(data_array[idx])
                                titanium_vals.append(val)
                            
                            if len(titanium_vals) > 0:
                                entry[f'Var_{i+1}'] = float(np.mean(titanium_vals))
                            else:
                                entry[f'Var_{i+1}'] = 0.0
                        else:
                            entry[f'Var_{i+1}'] = 0.0
                    except:
                        entry[f'Var_{i+1}'] = 0.0
                
                history_data.append(entry)
            except:
                continue
        
        server.shutdown()
        return history_data, total_titanium
        
    except:
        if 'server' in locals():
            server.shutdown()
        return [], 0


def generar_graficas_cfrp(all_results, output_folder):
    """Genera gráficas para análisis CFRP."""
    damage_colors = {
        1: '#1f77b4',
        2: '#ff7f0e',
        3: '#2ca02c',
        4: '#d62728',
        5: '#9467bd'
    }
    
    for damage_idx in range(1, 6):
        plt.figure(figsize=(10, 6))
        
        for case_name, data in all_results.items():
            damage_values = data[f'damage_{damage_idx}']
            plt.plot(data['time_values'], damage_values, label=case_name, linewidth=2)
        
        plt.xlabel('Tiempo (s)', fontsize=11)
        plt.ylabel('Elementos que Fallaron (Sum)', fontsize=11)
        plt.title(f'Evolución del daño - Damage {damage_idx}', fontsize=12)
        plt.legend(loc='best', fontsize=9)
        plt.grid(True, alpha=0.3, linestyle='--', linewidth=0.5)
        plt.tight_layout()
        
        graph_path = os.path.join(output_folder, f"DamageType{damage_idx}.png")
        plt.savefig(graph_path, dpi=300, bbox_inches='tight')
        plt.close()
    
    for case_name, data in all_results.items():
        plt.figure(figsize=(12, 7))
        
        for damage_idx in range(1, 6):
            color = damage_colors.get(damage_idx, '#000000')
            damage_values = data[f'damage_{damage_idx}']
            plt.plot(data['time_values'], damage_values, label=f'Damage {damage_idx}', color=color, linewidth=2)
        
        plt.xlabel('Tiempo (s)', fontsize=11)
        plt.ylabel('Elementos que Fallaron (Sum)', fontsize=11)
        plt.title(f'Evolución del daño - {case_name}', fontsize=12)
        plt.legend(loc='best', fontsize=10)
        plt.grid(True, alpha=0.3, linestyle='--', linewidth=0.5)
        plt.tight_layout()
        
        case_number = case_name.split('_')[1] if '_' in case_name else case_name
        graph_path = os.path.join(output_folder, f"Case_{case_number}_AllDamages.png")
        plt.savefig(graph_path, dpi=300, bbox_inches='tight')
        plt.close()


def generar_graficas_titanio(all_results, output_folder):
    """Genera gráficas para análisis Titanio."""
    var_names = {
        2: 'Stress Triaxiality',
        3: 'Plastic Strain',
        4: 'Temperature',
        5: 'Strain Rate'
    }
    
    var_colors = {
        2: '#1f77b4',
        3: '#2ca02c',
        4: '#d62728',
        5: '#9467bd'
    }
    
    for var_idx in range(2, 6):
        plt.figure(figsize=(10, 6))
        
        for case_name, data in all_results.items():
            var_values = data[f'var_{var_idx}']
            plt.plot(data['time_values'], var_values, label=case_name, linewidth=2)
        
        plt.xlabel('Tiempo (s)', fontsize=11)
        plt.ylabel(f'{var_names[var_idx]} (Promedio)', fontsize=11)
        plt.title(f'Evolución de {var_names[var_idx]}', fontsize=12)
        plt.legend(loc='best', fontsize=9)
        plt.grid(True, alpha=0.3, linestyle='--', linewidth=0.5)
        plt.tight_layout()
        
        graph_path = os.path.join(output_folder, f"Titanium_Var{var_idx}.png")
        plt.savefig(graph_path, dpi=300, bbox_inches='tight')
        plt.close()
    
    for case_name, data in all_results.items():
        fig, axes = plt.subplots(2, 2, figsize=(14, 10))
        axes = axes.flatten()
        
        for idx, var_idx in enumerate(range(2, 6)):
            color = var_colors.get(var_idx, '#000000')
            var_values = data[f'var_{var_idx}']
            axes[idx].plot(data['time_values'], var_values, label=var_names[var_idx], color=color, linewidth=2)
            axes[idx].set_xlabel('Tiempo (s)', fontsize=9)
            axes[idx].set_ylabel(var_names[var_idx], fontsize=9)
            axes[idx].set_title(var_names[var_idx], fontsize=10)
            axes[idx].grid(True, alpha=0.3)
        
        plt.suptitle(f'Variables Titanio - {case_name}', fontsize=14, y=0.98)
        plt.tight_layout(rect=[0, 0, 1, 0.96])
        
        case_number = case_name.split('_')[1] if '_' in case_name else case_name
        graph_path = os.path.join(output_folder, f"Titanium_Case_{case_number}_AllVars.png")
        plt.savefig(graph_path, dpi=300, bbox_inches='tight')
        plt.close()


def exportar_excel_cfrp(all_results, output_folder):
    """Exporta resultados CFRP a Excel."""
    excel_path = os.path.join(output_folder, "Damage_Catalog.xlsx")
    
    with pd.ExcelWriter(excel_path, engine='openpyxl') as writer:
        summary = []
        for case_name, data in all_results.items():
            summary.append({
                'Case': case_name,
                'Sequence': case_name.split('_')[-1] if '_' in case_name else 'N/A',
                'Total_CFRP_Elements': data.get('total_cfrp_elements', 'N/A'),
                'Time_Steps': len(data['time_values']),
                'Max_Time': round(max(data['time_values']), 4) if data['time_values'] else 0,
                'Final_D1': int(data['damage_1'][-1]) if data['damage_1'] else 0,
                'Final_D2': int(data['damage_2'][-1]) if data['damage_2'] else 0,
                'Final_D3': int(data['damage_3'][-1]) if data['damage_3'] else 0,
                'Final_D4': int(data['damage_4'][-1]) if data['damage_4'] else 0,
                'Final_D5': int(data['damage_5'][-1]) if data['damage_5'] else 0,
            })
        pd.DataFrame(summary).to_excel(writer, sheet_name='Summary', index=False)
        
        for case_name, data in all_results.items():
            df = pd.DataFrame({
                'Time_Step': range(len(data['time_values'])),
                'Time_Value': data['time_values'],
                'Damage_1': data['damage_1'],
                'Damage_2': data['damage_2'],
                'Damage_3': data['damage_3'],
                'Damage_4': data['damage_4'],
                'Damage_5': data['damage_5'],
            })
            df.to_excel(writer, sheet_name=case_name[:31], index=False)
    
    return excel_path


def exportar_excel_titanio(all_results, output_folder):
    """Exporta resultados Titanio a Excel."""
    excel_path = os.path.join(output_folder, "Titanium_History_Catalog.xlsx")
    
    with pd.ExcelWriter(excel_path, engine='openpyxl') as writer:
        summary = []
        for case_name, data in all_results.items():
            summary.append({
                'Case': case_name,
                'Titanium_Parts': str(get_part_ids(case_name, 'T')),
                'Total_Titanium_Elements': data.get('total_titanium_elements', 'N/A'),
                'Time_Steps': len(data['time_values']),
                'Max_Time': round(max(data['time_values']), 4) if data['time_values'] else 0,
                'Final_Triaxiality': round(data['var_2'][-1], 4) if data['var_2'] else 0,
                'Final_Plastic_Strain': round(data['var_3'][-1], 4) if data['var_3'] else 0,
                'Final_Temperature': round(data['var_4'][-1], 4) if data['var_4'] else 0,
                'Final_Strain_Rate': round(data['var_5'][-1], 4) if data['var_5'] else 0,
            })
        pd.DataFrame(summary).to_excel(writer, sheet_name='Summary', index=False)
        
        for case_name, data in all_results.items():
            df = pd.DataFrame({
                'Time_Step': range(len(data['time_values'])),
                'Time_Value': data['time_values'],
                'Stress_Triaxiality': data['var_2'],
                'Plastic_Strain': data['var_3'],
                'Temperature': data['var_4'],
                'Strain_Rate': data['var_5'],
            })
            df.to_excel(writer, sheet_name=case_name[:31], index=False)
    
    return excel_path


def analizar_cfrp(selected_path):
    """Ejecuta análisis completo para CFRP."""
    output_folder = os.path.join(selected_path, "RESULTS_CFRP_Damage")
    os.makedirs(output_folder, exist_ok=True)
    
    case_folders = []
    for item in os.listdir(selected_path):
        item_path = os.path.join(selected_path, item)
        if os.path.isdir(item_path) and item.startswith('case_'):
            case_folders.append((item, item_path))
    
    if not case_folders:
        return None
    
    all_results = {}
    
    for case_name, case_path in case_folders:
        cfrp_parts = get_part_ids(case_name, 'C')
        d3plot_file = find_d3plot(case_path)
        
        if not d3plot_file:
            continue
        
        damage_data, total_cfrp = extract_cfrp_damage_history(d3plot_file, cfrp_parts)
        
        if not damage_data:
            continue
        
        all_results[case_name] = {
            'time_values': [d['time_value'] for d in damage_data],
            'damage_1': [d['Damage_1'] for d in damage_data],
            'damage_2': [d['Damage_2'] for d in damage_data],
            'damage_3': [d['Damage_3'] for d in damage_data],
            'damage_4': [d['Damage_4'] for d in damage_data],
            'damage_5': [d['Damage_5'] for d in damage_data],
            'total_cfrp_elements': total_cfrp,
            'path': d3plot_file
        }
    
    if not all_results:
        return None
    
    generar_graficas_cfrp(all_results, output_folder)
    exportar_excel_cfrp(all_results, output_folder)
    
    return output_folder, len(case_folders)


def analizar_titanio(selected_path):
    """Ejecuta análisis completo para Titanio."""
    output_folder = os.path.join(selected_path, "RESULTS_TITANIUM_Damage")
    os.makedirs(output_folder, exist_ok=True)
    
    case_folders = []
    for item in os.listdir(selected_path):
        item_path = os.path.join(selected_path, item)
        if os.path.isdir(item_path) and item.startswith('case_'):
            case_folders.append((item, item_path))
    
    if not case_folders:
        return None
    
    all_results = {}
    
    for case_name, case_path in case_folders:
        titanium_parts = get_part_ids(case_name, 'T')
        d3plot_file = find_d3plot(case_path)
        
        if not d3plot_file:
            continue
        
        history_data, total_titanium = extract_titanium_history(d3plot_file, titanium_parts)
        
        if not history_data:
            continue
        
        all_results[case_name] = {
            'time_values': [d['time_value'] for d in history_data],
            'var_2': [d['Var_2'] for d in history_data],
            'var_3': [d['Var_3'] for d in history_data],
            'var_4': [d['Var_4'] for d in history_data],
            'var_5': [d['Var_5'] for d in history_data],
            'total_titanium_elements': total_titanium,
            'path': d3plot_file
        }
    
    if not all_results:
        return None
    
    generar_graficas_titanio(all_results, output_folder)
    exportar_excel_titanio(all_results, output_folder)
    
    return output_folder, len(case_folders)


def main():
    """Función principal - ejecuta ambos análisis automáticamente."""
    selected_path = seleccionar_carpeta("Seleccionar carpeta con casos")
    
    if not selected_path:
        return
    
    case_folders = [item for item in os.listdir(selected_path) 
                    if os.path.isdir(os.path.join(selected_path, item)) and item.startswith('case_')]
    
    print(f"Subcarpetas encontradas: {len(case_folders)}")
    
    print("Iniciando análisis CFRP")
    resultado_cfrp = analizar_cfrp(selected_path)
    if resultado_cfrp:
        output_folder, _ = resultado_cfrp
        print(f"Informacion guardada en {output_folder}")
    
    print("Iniciando análisis Titanio")
    resultado_ti = analizar_titanio(selected_path)
    if resultado_ti:
        output_folder, _ = resultado_ti
        print(f"Informacion guardada en {output_folder}")


if __name__ == "__main__":
    try:
        main()
    except Exception:
        pass