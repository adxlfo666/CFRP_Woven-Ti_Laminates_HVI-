"""
Instrucciones:
1. Ejecutar el código
2. Seleccionar la carpeta que contiene subcarpetas con imágenes
3. El programa automáticamente:
   - Detectará las coordenadas de recorte en la primera imagen
   - Recortará todas las imágenes
   - Analizará el área ROJA (delaminación) en cada imagen
   - Guardará los resultados en un archivo CSV
"""

import cv2
import numpy as np
import os
import tkinter as tk
from tkinter import filedialog
import pandas as pd
from pathlib import Path
from datetime import datetime


def seleccionar_carpeta(titulo="Selecciona una carpeta"):
    """Abre una ventana emergente para seleccionar una carpeta."""
    root = tk.Tk()
    root.withdraw()
    root.attributes('-topmost', True)
    carpeta = filedialog.askdirectory(title=titulo, mustexist=True)
    root.destroy()
    return carpeta if carpeta else None


def detectar_coordenadas_recorte(ruta_imagen):
    """
    Detecta automáticamente las coordenadas de la placa/gráfico
    ignorando el fondo blanco.
    """
    img = cv2.imread(ruta_imagen)
    if img is None:
        return None
        
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    _, mask = cv2.threshold(gray, 230, 255, cv2.THRESH_BINARY_INV)
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    
    if contours:
        c = max(contours, key=cv2.contourArea)
        x, y, w, h = cv2.boundingRect(c)
        return x, y, w, h
    return None


def analizar_area_roja(img, tamaño_placa_mm=310):
    """
    Analiza únicamente el color ROJO en la imagen.
    Retorna área en mm² y porcentaje de delaminación.
    """
    h, w = img.shape[:2]
    
    mm_por_pixel_x = tamaño_placa_mm / w
    mm_por_pixel_y = tamaño_placa_mm / h
    area_por_pixel = mm_por_pixel_x * mm_por_pixel_y
    
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)

    lower_rojo1 = np.array([0, 100, 100])
    upper_rojo1 = np.array([15, 255, 255])
    
    lower_rojo2 = np.array([160, 100, 100])
    upper_rojo2 = np.array([180, 255, 255])

    mask1 = cv2.inRange(hsv, lower_rojo1, upper_rojo1)
    mask2 = cv2.inRange(hsv, lower_rojo2, upper_rojo2)
    mask_final = cv2.bitwise_or(mask1, mask2)

    pixeles_rojos = cv2.countNonZero(mask_final)
    area_mm2 = pixeles_rojos * area_por_pixel
    
    area_total_placa_mm2 = tamaño_placa_mm * tamaño_placa_mm
    porcentaje = (area_mm2 / area_total_placa_mm2) * 100

    return {
        "area_mm2": round(area_mm2, 2),
        "porcentaje_delaminacion": round(porcentaje, 2)
    }


def procesar_todo_en_uno():
    """
    Flujo completo:
    1. Selecciona carpeta con subcarpetas de imágenes
    2. Detecta coordenadas de recorte en la primera imagen
    3. Recorta TODAS las imágenes
    4. Analiza el área ROJA en cada imagen recortada
    5. Guarda resultados en CSV
    """
    carpeta_base = seleccionar_carpeta(
        "Selecciona la CARPETA RAÍZ (que contiene subcarpetas con imágenes)"
    )
    
    if not carpeta_base:
        return

    ruta_base = Path(carpeta_base)
    carpetas = [d for d in ruta_base.iterdir() if d.is_dir()]
    
    if not carpetas:
        return
    
    print(f"Subcarpetas encontradas: {len(carpetas)}")
    
    coordenadas = None
    primera_imagen_encontrada = None
    
    for carpeta in sorted(carpetas):
        imagenes = list(carpeta.glob("*.jpg")) + list(carpeta.glob("*.png")) + list(carpeta.glob("*.jpeg"))
        imagenes = [img for img in imagenes if "recortadas" not in str(img)]
        if imagenes:
            primera_imagen_encontrada = imagenes[0]
            break
    
    if primera_imagen_encontrada:
        coordenadas = detectar_coordenadas_recorte(str(primera_imagen_encontrada))
    
    if not primera_imagen_encontrada:
        return

    print("Iniciando procesamiento...")
    
    resultados = []
    total_imagenes = 0
    
    for carpeta in carpetas:
        imagenes = list(carpeta.glob("*.jpg")) + list(carpeta.glob("*.png")) + list(carpeta.glob("*.jpeg"))
        imagenes = [img for img in imagenes if "recortadas" not in str(img)]
        total_imagenes += len(imagenes)
    
    print(f"Total de imágenes a procesar: {total_imagenes}")
    
    for carpeta in sorted(carpetas):
        carpeta_recortadas = carpeta / "recortadas"
        carpeta_recortadas.mkdir(exist_ok=True)
        
        imagenes = list(carpeta.glob("*.jpg")) + list(carpeta.glob("*.png")) + list(carpeta.glob("*.jpeg"))
        imagenes = [img for img in imagenes if "recortadas" not in str(img)]
        imagenes.sort()
        
        for ruta_imagen in imagenes:
            img = cv2.imread(str(ruta_imagen))
            if img is None:
                continue
            
            if coordenadas:
                x, y, w, h = coordenadas
                h_img, w_img = img.shape[:2]
                if x + w > w_img:
                    w = w_img - x
                if y + h > h_img:
                    h = h_img - y
                img_recortada = img[y:y+h, x:x+w]
            else:
                img_recortada = img
            
            ruta_recortada = carpeta_recortadas / ruta_imagen.name
            cv2.imwrite(str(ruta_recortada), img_recortada)
            
            analisis = analizar_area_roja(img_recortada)
            
            resultados.append({
                "carpeta": carpeta.name,
                "archivo": ruta_imagen.name,
                "area_mm2": analisis["area_mm2"],
                "porcentaje_delaminacion": analisis["porcentaje_delaminacion"]
            })
    
    if resultados:
        df = pd.DataFrame(resultados)
        
        try:
            df['numero'] = df['archivo'].str.extract(r'(\d+)').astype(float)
            df = df.sort_values(['carpeta', 'numero']).reset_index(drop=True)
            df = df.drop('numero', axis=1)
        except Exception:
            df = df.sort_values(['carpeta', 'archivo']).reset_index(drop=True)
        
        nombre_salida = "Reporte_Delaminacion.csv"
        ruta_salida = os.path.join(carpeta_base, nombre_salida)
        
        df.to_csv(ruta_salida, index=False, encoding='utf-8-sig')
        
        print(f"Informacion guardada en {ruta_salida}")


if __name__ == "__main__":
    try:
        procesar_todo_en_uno()
    except Exception:
        pass