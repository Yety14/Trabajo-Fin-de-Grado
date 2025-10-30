import psutil
import requests
import time
import socket

# ===== CONFIGURACIÓN =====
MASTER_IP = '10.160.37.73'
MASTER_PORT = 5000
NODE_ID = socket.gethostname()
ENERGY_WATTS = 120
UPDATE_INTERVAL = 10

def get_cpu_temp_linux():
    try:
        with open("/sys/class/thermal/thermal_zone0/temp", "r") as f:
            temp_str = f.read()
            temp_c = int(temp_str) / 1000
            if 0 < temp_c < 110:
                return temp_c
    except Exception:
        pass
    try:
        temps = psutil.sensors_temperatures()
        for key in ["coretemp", "k10temp", "cpu_thermal"]:
            if key in temps and temps[key]:
                return round(sum([t.current for t in temps[key]]) / len(temps[key]), 1)
    except Exception:
        pass
    return None

def get_hardware_info():
    return {
        "node_id": NODE_ID,
        "cpu_percent": psutil.cpu_percent(interval=1),
        "ram_percent": psutil.virtual_memory().percent,
        "cpu_temp": get_cpu_temp_linux(),
        "power_watts": ENERGY_WATTS
    }

def send_metrics():
    try:
        metrics = get_hardware_info()
        url = f"http://{MASTER_IP}:{MASTER_PORT}/update_metrics"
        requests.post(url, json=metrics, timeout=5)
        print(f"Métricas enviadas: {metrics}")
        return True
    except Exception as e:
        print(f"Error enviando métricas: {e}")
        return False

if __name__ == "__main__":
    print(f"\n🖥️ Nodo Dinámico: {NODE_ID}")
    print(f"🎯 Maestro: {MASTER_IP}:{MASTER_PORT}\n")
    while True:
        try:
            send_metrics()
            time.sleep(UPDATE_INTERVAL)
        except KeyboardInterrupt:
            print("\n👋 Deteniendo esclavo...")
            break
        except Exception as e:
            print(f"Error: {e}")
            time.sleep(5)
