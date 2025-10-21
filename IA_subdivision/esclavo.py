import psutil
import requests
import time
import socket
import subprocess

# ===== CONFIGURACIÓN =====
MASTER_IP = '10.160.37.73'
MASTER_PORT = 5000
NODE_ID = socket.gethostname()
ENERGY_WATTS = 120
UPDATE_INTERVAL = 10


# ===== FUNCIONES =====

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
        "cpu_cores": psutil.cpu_count(),
        "cpu_percent": psutil.cpu_percent(interval=1),
        "ram_total_GB": round(psutil.virtual_memory().total / (1024 ** 3), 2),
        "ram_percent": psutil.virtual_memory().percent,
        "cpu_temp": get_cpu_temp_linux()
    }


def register_with_master():
    try:
        url = f"http://{MASTER_IP}:{MASTER_PORT}/register"
        data = {"node_id": NODE_ID, "energy_watts": ENERGY_WATTS}
        response = requests.post(url, json=data, timeout=5)
        if response.status_code == 200:
            print(f"✅ Registrado en el maestro")
            return True
    except Exception as e:
        print(f"❌ Error al registrar: {e}")
    return False


def send_metrics():
    try:
        metrics = get_hardware_info()
        url = f"http://{MASTER_IP}:{MASTER_PORT}/update_metrics"
        requests.post(url, json=metrics, timeout=5)
        return True
    except:
        return False


def request_task():
    """Pide una tarea al maestro"""
    try:
        url = f"http://{MASTER_IP}:{MASTER_PORT}/request_task"
        data = {"node_id": NODE_ID}
        response = requests.post(url, json=data, timeout=5)

        if response.status_code == 200:
            result = response.json()
            if result['status'] == 'task_assigned':
                return result['task']
            elif result['status'] == 'no_tasks':
                return None
            elif result['status'] == 'rejected':
                print(f"⚠️ Rechazado: {result['reason']}")
                return None
    except Exception as e:
        print(f"❌ Error al pedir tarea: {e}")
    return None


def execute_task(task):
    """Ejecuta la tarea asignada"""
    print(f"⚙️  Ejecutando tarea {task['task_id']}: {task['data']}")

    # AQUÍ VAN TUS TAREAS REALES
    task_type = task['data'].get('type')

    try:
        if task_type == 'train_model':
            # Ejemplo: entrenar modelo
            result = train_model(task['data'])
        elif task_type == 'process_data':
            # Ejemplo: procesar datos
            result = process_data(task['data'])
        elif task_type == 'simulation':
            # Ejemplo: simulación
            result = run_simulation(task['data'])
        else:
            # Tarea genérica
            time.sleep(5)  # Simular trabajo
            result = {"status": "completed"}

        return result, True
    except Exception as e:
        print(f"❌ Error ejecutando tarea: {e}")
        return {"error": str(e)}, False


def train_model(data):
    """Ejemplo de función de entrenamiento"""
    epochs = data.get('epochs', 10)
    print(f"   Entrenando modelo por {epochs} epochs...")
    time.sleep(epochs * 0.5)  # Simular entrenamiento
    return {"model": "trained", "accuracy": 0.95}


def process_data(data):
    """Ejemplo de función de procesamiento"""
    file = data.get('file')
    print(f"   Procesando {file}...")
    time.sleep(3)
    return {"processed_rows": 1000}


def run_simulation(data):
    """Ejemplo de función de simulación"""
    params = data.get('params', {})
    print(f"   Ejecutando simulación con {params}...")
    time.sleep(4)
    return {"result": "simulation_complete"}


def complete_task(task_id, result, success):
    """Reporta la tarea como completada"""
    try:
        url = f"http://{MASTER_IP}:{MASTER_PORT}/complete_task"
        data = {
            "task_id": task_id,
            "node_id": NODE_ID,
            "result": result,
            "success": success
        }
        response = requests.post(url, json=data, timeout=5)
        return response.status_code == 200
    except Exception as e:
        print(f"❌ Error reportando tarea: {e}")
        return False


# ===== BUCLE PRINCIPAL =====

if __name__ == "__main__":
    print(f"\n🖥️  Nodo Esclavo Dinámico: {NODE_ID}")
    print(f"🎯 Maestro: {MASTER_IP}:{MASTER_PORT}\n")

    register_with_master()

    last_metric_update = 0

    while True:
        try:
            # Actualizar métricas periódicamente
            if time.time() - last_metric_update > UPDATE_INTERVAL:
                send_metrics()
                last_metric_update = time.time()

            # Pedir tarea
            task = request_task()

            if task:
                # Ejecutar tarea
                result, success = execute_task(task)

                # Reportar completada
                complete_task(task['task_id'], result, success)
            else:
                # No hay tareas, esperar
                print("💤 Sin tareas, esperando...")
                time.sleep(5)

        except KeyboardInterrupt:
            print("\n👋 Deteniendo esclavo...")
            break
        except Exception as e:
            print(f"❌ Error: {e}")
            time.sleep(5)
