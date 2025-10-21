import time
from datetime import datetime
from flask import Flask, request, jsonify
import queue


class MasterAgent:
    def __init__(self, weights=None):
        # ... (tu código anterior de ponderaciones y config) ...
        self.weights = weights or {
            "cpu_availability": 0.30,
            "ram_availability": 0.25,
            "temperature": 0.15,
            "energy_efficiency": 0.20,
            "historical_performance": 0.10
        }

        self.config = {
            "temp_max": 85,
            "temp_warning": 75,
            "ram_critical": 95,
            "cpu_critical": 95
        }

        self.energy_consumption = {}
        self.performance_history = {}
        self.decision_log = []
        self.nodes_data = {}

        # NUEVO: Cola de tareas pendientes
        self.task_queue = queue.Queue()
        self.active_tasks = {}  # {task_id: {node_id, start_time, task_data}}
        self.completed_tasks = []
        self.task_id_counter = 0

    def add_task(self, task_data):
        """Añade una tarea a la cola"""
        self.task_id_counter += 1
        task = {
            'task_id': self.task_id_counter,
            'data': task_data,
            'created_at': datetime.now().isoformat()
        }
        self.task_queue.put(task)
        print(f"➕ Tarea {task['task_id']} añadida a la cola")
        return task['task_id']

    def get_next_task_for_node(self, node_id):
        """Obtiene la siguiente tarea para un nodo específico"""
        if self.task_queue.empty():
            return None

        try:
            task = self.task_queue.get_nowait()
            self.active_tasks[task['task_id']] = {
                'node_id': node_id,
                'start_time': time.time(),
                'task_data': task
            }
            print(f"📤 Tarea {task['task_id']} asignada a {node_id}")
            return task
        except queue.Empty:
            return None

    def complete_task(self, task_id, node_id, result, success=True):
        """Marca una tarea como completada"""
        if task_id in self.active_tasks:
            task_info = self.active_tasks[task_id]
            elapsed_time = time.time() - task_info['start_time']

            # Actualizar historial de rendimiento del nodo
            self.update_performance(node_id, elapsed_time, success)

            # Guardar resultado
            self.completed_tasks.append({
                'task_id': task_id,
                'node_id': node_id,
                'elapsed_time': elapsed_time,
                'success': success,
                'result': result,
                'completed_at': datetime.now().isoformat()
            })

            del self.active_tasks[task_id]
            print(f"✅ Tarea {task_id} completada por {node_id} en {elapsed_time:.2f}s")
            return True
        return False

    def get_queue_status(self):
        """Devuelve el estado de la cola de tareas"""
        return {
            'pending_tasks': self.task_queue.qsize(),
            'active_tasks': len(self.active_tasks),
            'completed_tasks': len(self.completed_tasks)
        }

    # ... (resto de métodos anteriores: calculate_node_score, etc.) ...

    def register_node(self, node_id, energy_watts=100):
        """Registra un nuevo nodo esclavo"""
        self.energy_consumption[node_id] = energy_watts
        self.performance_history[node_id] = {
            "tasks_completed": 0,
            "total_time": 0,
            "avg_time": 0,
            "failures": 0,
            "success_rate": 1.0
        }
        print(f"✅ Nodo {node_id} registrado")

    def update_node_data(self, node_id, node_data):
        """Actualiza los datos de un nodo esclavo"""
        self.nodes_data[node_id] = node_data
        if node_id not in self.energy_consumption:
            self.register_node(node_id)

    def calculate_node_score(self, node_id, node_data, system_load="normal"):
        """Calcula puntuación del nodo"""
        cpu_percent = node_data.get("cpu_percent", 100)
        ram_percent = node_data.get("ram_percent", 100)
        cpu_temp = node_data.get("cpu_temp", None)

        if cpu_temp and cpu_temp > self.config["temp_max"]:
            return 0.0
        if ram_percent > self.config["ram_critical"]:
            return 0.0
        if cpu_percent > self.config["cpu_critical"]:
            return 0.0

        score_cpu = (100 - cpu_percent) / 100
        score_ram = (100 - ram_percent) / 100

        if cpu_temp is not None:
            score_temp = max(0, (self.config["temp_max"] - cpu_temp) / self.config["temp_max"])
        else:
            score_temp = 0.5

        node_energy = self.energy_consumption.get(node_id, 100)
        max_energy = max(self.energy_consumption.values()) if self.energy_consumption else 100
        score_energy = 1 - (node_energy / max_energy)

        perf = self.performance_history.get(node_id, {"success_rate": 0.5})
        score_history = perf["success_rate"]

        weights = self.weights.copy()
        if system_load == "low":
            weights["energy_efficiency"] *= 1.5
            weights["cpu_availability"] *= 0.7
        elif system_load == "high":
            weights["cpu_availability"] *= 1.3
            weights["temperature"] *= 1.3
            weights["energy_efficiency"] *= 0.5

        total_weight = sum(weights.values())
        weights = {k: v / total_weight for k, v in weights.items()}

        final_score = (
                score_cpu * weights["cpu_availability"] +
                score_ram * weights["ram_availability"] +
                score_temp * weights["temperature"] +
                score_energy * weights["energy_efficiency"] +
                score_history * weights["historical_performance"]
        )
        return final_score

    def update_performance(self, node_id, task_time, success=True):
        """Actualiza el historial de rendimiento"""
        if node_id not in self.performance_history:
            self.register_node(node_id)

        perf = self.performance_history[node_id]

        if success:
            perf["tasks_completed"] += 1
            perf["total_time"] += task_time
            perf["avg_time"] = perf["total_time"] / perf["tasks_completed"]
        else:
            perf["failures"] += 1

        total_tasks = perf["tasks_completed"] + perf["failures"]
        perf["success_rate"] = perf["tasks_completed"] / total_tasks if total_tasks > 0 else 0.5


# === SERVIDOR FLASK ===

app = Flask(__name__)
master = None


@app.route('/register', methods=['POST'])
def register_node():
    data = request.get_json()
    node_id = data.get('node_id')
    energy_watts = data.get('energy_watts', 100)

    if not node_id:
        return jsonify({"error": "node_id requerido"}), 400

    master.register_node(node_id, energy_watts)
    return jsonify({"status": "registered", "node_id": node_id}), 200


@app.route('/update_metrics', methods=['POST'])
def update_metrics():
    data = request.get_json()
    node_id = data.get('node_id') or request.remote_addr

    metrics = {
        "cpu_cores": data.get("cpu_cores"),
        "cpu_percent": data.get("cpu_percent"),
        "ram_total_GB": data.get("ram_total_GB"),
        "ram_percent": data.get("ram_percent"),
        "cpu_temp": data.get("cpu_temp")
    }

    master.update_node_data(node_id, metrics)
    return jsonify({"status": "updated", "node_id": node_id}), 200


@app.route('/request_task', methods=['POST'])
def request_task():
    """Endpoint para que un esclavo pida una tarea"""
    data = request.get_json()
    node_id = data.get('node_id') or request.remote_addr

    # Verificar que el nodo esté en buen estado
    if node_id in master.nodes_data:
        score = master.calculate_node_score(node_id, master.nodes_data[node_id])
        if score < 0.3:  # Umbral mínimo
            return jsonify({
                "status": "rejected",
                "reason": "Node score too low",
                "score": score
            }), 200

    # Obtener siguiente tarea
    task = master.get_next_task_for_node(node_id)

    if task:
        return jsonify({
            "status": "task_assigned",
            "task": task
        }), 200
    else:
        return jsonify({
            "status": "no_tasks",
            "message": "No hay tareas pendientes"
        }), 200


@app.route('/complete_task', methods=['POST'])
def complete_task():
    """Endpoint para reportar tarea completada"""
    data = request.get_json()
    task_id = data.get('task_id')
    node_id = data.get('node_id')
    result = data.get('result')
    success = data.get('success', True)

    if not task_id or not node_id:
        return jsonify({"error": "task_id y node_id requeridos"}), 400

    if master.complete_task(task_id, node_id, result, success):
        return jsonify({"status": "completed"}), 200
    else:
        return jsonify({"error": "Task not found"}), 404


@app.route('/add_task', methods=['POST'])
def add_task():
    """Endpoint para añadir tareas a la cola (para testing o cliente externo)"""
    data = request.get_json()
    task_data = data.get('task_data')

    if not task_data:
        return jsonify({"error": "task_data requerido"}), 400

    task_id = master.add_task(task_data)
    return jsonify({"status": "task_added", "task_id": task_id}), 200


@app.route('/queue_status', methods=['GET'])
def queue_status():
    """Endpoint para ver el estado de la cola"""
    return jsonify(master.get_queue_status()), 200


@app.route('/status', methods=['GET'])
def get_status():
    """Estado completo del clúster"""
    status = {
        'nodes': master.nodes_data,
        'queue': master.get_queue_status(),
        'active_tasks': master.active_tasks,
        'timestamp': datetime.now().isoformat()
    }
    return jsonify(status), 200


if __name__ == "__main__":
    custom_weights = {
        "cpu_availability": 0.35,
        "ram_availability": 0.30,
        "temperature": 0.15,
        "energy_efficiency": 0.15,
        "historical_performance": 0.05
    }

    master = MasterAgent(weights=custom_weights)

    # Añadir algunas tareas de ejemplo
    master.add_task({"type": "train_model", "epochs": 10})
    master.add_task({"type": "process_data", "file": "data1.csv"})
    master.add_task({"type": "simulation", "params": {"x": 100}})

    print("\n🚀 Servidor maestro con cola de tareas iniciado")
    print("📡 Endpoints:")
    print("   - POST /request_task    : Pedir tarea")
    print("   - POST /complete_task   : Reportar tarea completada")
    print("   - POST /add_task        : Añadir tarea a la cola")
    print("   - GET  /queue_status    : Ver estado de la cola\n")

    app.run(host='0.0.0.0', port=5000, debug=False)
