import json
import os
import shutil
import zipfile

TARGET_MODEL = os.path.join("model", "mobilenetv2_penyakit_daun.keras")
BACKUP_MODEL = TARGET_MODEL + ".bak"
TEMP_MODEL = TARGET_MODEL + ".tmp"


def clean_config(obj):
  if isinstance(obj, dict):
    obj.pop("quantization_config", None)
    for v in obj.values():
      clean_config(v)
  elif isinstance(obj, list):
    for item in obj:
      clean_config(item)


shutil.copy2(TARGET_MODEL, BACKUP_MODEL)

with zipfile.ZipFile(TARGET_MODEL, "r") as zin, zipfile.ZipFile(
    TEMP_MODEL, "w", zipfile.ZIP_DEFLATED
) as zout:
  for item in zin.infolist():
    content = zin.read(item.filename)
    if item.filename == "config.json":
      config_data = json.loads(content.decode("utf-8"))
      clean_config(config_data)
      content = json.dumps(config_data).encode("utf-8")
    zout.writestr(item, content)

os.replace(TEMP_MODEL, TARGET_MODEL)
print("Berhasil memperbaiki:", TARGET_MODEL)