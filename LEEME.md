# Estudio de certificaciones (v1)

## Publicar en GitHub Pages
1. Crea un repositorio y sube el contenido de esta carpeta (index.html, data/, .nojekyll).
2. En Settings > Pages, elige la rama main y la carpeta raíz.
3. Los empleados entran por la dirección que te da GitHub. No hace falta nada más.

El progreso se guarda en el navegador de cada persona (clave propia por certificación).
Para cambiar de equipo: Datos y ajustes > Exportar progreso, y en el otro navegador > Importar.

## Añadir otra certificación
1. Prepara el Word con el mismo formato (Pregunta N / Respuesta, enlaces oficiales).
2. Ejecuta (requiere pandoc y Python 3):
   python herramientas/convert.py examen.docx --id az-900 --out data/az900 --media-url data/az900/media
3. Añade una entrada en data/catalog.json: {"id":"az-900","name":"...","subtitle":"...","file":"data/az900/questions.json","questions":N}
4. Revisa data/az900/report.txt (problemas detectados al convertir).

Nota: el nombre y subtítulo de la certificación dentro de questions.json están fijados en convert.py (variable `pack`); cámbialos antes de convertir otra.
