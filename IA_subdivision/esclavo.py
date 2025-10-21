import psutil
import requests
import time
import socket

# ===== CONFIGURACIÓN =====
MASTER_IP = '10.160.37.73'  # Cambia por la IP de tu maestro
MASTER_PORT = 5000
NODE_ID = socket.gethostname()  # Usa el nombre del equipo como ID
ENERGY_WATTS = 120  # Consumo energético estimado de este nodo (ajústalo)
UPDATE_INTERVAL = 10  # Segundos entre actualizaciones


# ===== FUNCIONES =====

def get_cpu_temp_linux():
    """Obtiene la temperatura de la CPU en Linux"""
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
    """Recopila información del hardware"""
    return {
        "node_id": NODE_ID,
        "cpu_cores": psutil.cpu_count(),
        "cpu_percent": psutil.cpu_percent(interval=1),
        "ram_total_GB": round(psutil.virtual_memory().total / (1024 ** 3), 2),
        "ram_percent": psutil.virtual_memory().percent,
        "cpu_temp": get_cpu_temp_linux()
    }


def register_with_master():
    """Registra este nodo con el maestro"""
    try:
        url = f"http://{MASTER_IP}:{MASTER_PORT}/register"
        data = {
            "node_id": NODE_ID,
            "energy_watts": ENERGY_WATTS
        }
        response = requests.post(url, json=data, timeout=5)
        if response.status_code == 200:
            print(f"✅ Nodo {NODE_ID} registrado en el maestro")
            return True
        else:
            print(f"⚠️ Error al registrar: {response.status_code}")
            return False
    except Exception as e:
        print(f"❌ No se pudo conectar al maestro: {e}")
        return False


def send_metrics_to_master(metrics):
    """Envía las métricas al servidor maestro"""
    try:
        url = f"http://{MASTER_IP}:{MASTER_PORT}/update_metrics"
        response = requests.post(url, json=metrics, timeout=5)

        if response.status_code == 200:
            print(
                f"📤 Métricas enviadas: CPU={metrics['cpu_percent']:.1f}%, RAM={metrics['ram_percent']:.1f}%, Temp={metrics['cpu_temp']}°C")
            return True
        else:
            print(f"⚠️ Error al enviar métricas: {response.status_code}")
            return False
    except requests.exceptions.RequestException as e:
        print(f"❌ No se pudo conectar al maestro: {e}")
        return False


# ===== BUCLE PRINCIPAL =====

if __name__ == "__main__":
    print(f"\n🖥️  Nodo Esclavo: {NODE_ID}")
    print(f"🎯 Maestro: {MASTER_IP}:{MASTER_PORT}")
    print(f"⚡ Consumo: {ENERGY_WATTS}W")
    print(f"🔄 Intervalo de actualización: {UPDATE_INTERVAL}s\n")

    # Intentar registrarse con el maestro
    register_with_master()

    # Bucle infinito de envío de métricas
    while True:
        try:
            # Recopilar métricas
            metrics = get_hardware_info()

            # Enviar al maestro
            send_metrics_to_master(metrics)

            # Esperar antes de la próxima actualización
            time.sleep(UPDATE_INTERVAL)

        except KeyboardInterrupt:
            print("\n👋 Deteniendo nodo esclavo...")
            break
        except Exception as e:
            print(f"❌ Error inesperado: {e}")
            time.sleep(UPDATE_INTERVAL)
