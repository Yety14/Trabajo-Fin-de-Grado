import json
import time
from datetime import datetime
from flask import Flask, request, jsonify
import threading


class MasterAgent:
    def __init__(self, weights=None):
        # Ponderaciones configurables
        self.weights = weights or {
            "cpu_availability": 0.30,
            "ram_availability": 0.25,
            "temperature": 0.15,
            "energy_efficiency": 0.20,
            "historical_performance": 0.10
        }

        # Validar que suman 1
        total = sum(self.weights.values())
        if abs(total - 1.0) > 0.01:
            raise ValueError(f"Las ponderaciones deben sumar 1.0 (actual: {total})")

        # Configuración de umbrales
        self.config = {
            "temp_max": 85,  # Temperatura máxima antes de bloquear nodo
            "temp_warning": 75,  # Temperatura de advertencia
            "ram_critical": 95,  # RAM crítica, no asignar tareas
            "cpu_critical": 95  # CPU crítica
        }

        # Consumo energético estimado por nodo (en watts)
        self.energy_consumption = {}

        # Historial de rendimiento
        self.performance_history = {}

        # Registro de decisiones para aprendizaje
        self.decision_log = []

        # Datos actuales de los nodos (recibidos en tiempo real)
        self.nodes_data = {}

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
        print(f"✅ Nodo {node_id} registrado con {energy_watts}W")

    def update_node_data(self, node_id, node_data):
        """Actualiza los datos de un nodo esclavo"""
        self.nodes_data[node_id] = node_data

        # Auto-registrar nodo si no existe
        if node_id not in self.energy_consumption:
            self.register_node(node_id)

    def calculate_node_score(self, node_id, node_data, system_load="normal"):
        """
        Calcula puntuación de un nodo basado en métricas y ponderaciones

        Args:
            node_id: ID del nodo
            node_data: Diccionario con métricas del nodo
            system_load: "low", "normal", "high" - ajusta prioridades dinámicamente

        Returns:
            float: Puntuación entre 0 y 1 (mayor es mejor)
        """

        # Extraer datos
        cpu_percent = node_data.get("cpu_percent", 100)
        ram_percent = node_data.get("ram_percent", 100)
        cpu_temp = node_data.get("cpu_temp", None)

        # Si temperatura o recursos críticos, retornar 0
        if cpu_temp and cpu_temp > self.config["temp_max"]:
            return 0.0
        if ram_percent > self.config["ram_critical"]:
            return 0.0
        if cpu_percent > self.config["cpu_critical"]:
            return 0.0

        # === CALCULAR SCORES INDIVIDUALES (0 a 1) ===

        # 1. CPU disponible (invertido)
        score_cpu = (100 - cpu_percent) / 100

        # 2. RAM disponible (invertido)
        score_ram = (100 - ram_percent) / 100

        # 3. Temperatura (normalizado, menor es mejor)
        if cpu_temp is not None:
            score_temp = max(0, (self.config["temp_max"] - cpu_temp) / self.config["temp_max"])
        else:
            score_temp = 0.5  # Valor neutro si no hay temperatura

        # 4. Eficiencia energética (normalizado)
        node_energy = self.energy_consumption.get(node_id, 100)
        max_energy = max(self.energy_consumption.values()) if self.energy_consumption else 100
        score_energy = 1 - (node_energy / max_energy)

        # 5. Rendimiento histórico
        perf = self.performance_history.get(node_id, {"success_rate": 0.5})
        score_history = perf["success_rate"]

        # === AJUSTE DINÁMICO DE PESOS SEGÚN CARGA DEL SISTEMA ===
        weights = self.weights.copy()

        if system_load == "low":
            # Con poca carga, priorizar eficiencia energética
            weights["energy_efficiency"] *= 1.5
            weights["cpu_availability"] *= 0.7
        elif system_load == "high":
            # Con mucha carga, priorizar disponibilidad y temperatura
            weights["cpu_availability"] *= 1.3
            weights["temperature"] *= 1.3
            weights["energy_efficiency"] *= 0.5

        # Renormalizar pesos
        total_weight = sum(weights.values())
        weights = {k: v / total_weight for k, v in weights.items()}

        # === CALCULAR SCORE FINAL PONDERADO ===
        final_score = (
                score_cpu * weights["cpu_availability"] +
                score_ram * weights["ram_availability"] +
                score_temp * weights["temperature"] +
                score_energy * weights["energy_efficiency"] +
                score_history * weights["historical_performance"]
        )

        return final_score

    def select_best_node(self, system_load="normal"):
        """
        Selecciona el mejor nodo para asignar una tarea usando datos en tiempo real

        Args:
            system_load: nivel de carga del sistema

        Returns:
            tuple: (node_id, score, scores_detail)
        """
        if not self.nodes_data:
            return None, 0, {}

        best_node = None
        best_score = -1
        scores_detail = {}

        for node_id, data in self.nodes_data.items():
            score = self.calculate_node_score(node_id, data, system_load)
            scores_detail[node_id] = score

            if score > best_score:
                best_score = score
                best_node = node_id

        # Registrar decisión
        self.decision_log.append({
            "timestamp": datetime.now().isoformat(),
            "selected_node": best_node,
            "score": best_score,
            "all_scores": scores_detail,
            "system_load": system_load
        })

        return best_node, best_score, scores_detail

    def update_performance(self, node_id, task_time, success=True):
        """
        Actualiza el historial de rendimiento tras completar una tarea
        Aquí es donde la IA "aprende"
        """
        if node_id not in self.performance_history:
            self.register_node(node_id)

        perf = self.performance_history[node_id]

        if success:
            perf["tasks_completed"] += 1
            perf["total_time"] += task_time
            perf["avg_time"] = perf["total_time"] / perf["tasks_completed"]
        else:
            perf["failures"] += 1

        # Calcular tasa de éxito
        total_tasks = perf["tasks_completed"] + perf["failures"]
        perf["success_rate"] = perf["tasks_completed"] / total_tasks if total_tasks > 0 else 0.5

    def adjust_weights_from_history(self):
        """
        Ajusta automáticamente las ponderaciones basándose en el historial
        (Aprendizaje simple - puedes mejorarlo con ML real)
        """
        # Analizar últimas 100 decisiones
        recent_decisions = self.decision_log[-100:]

        if len(recent_decisions) < 10:
            return  # Necesita más datos

        print("⚙️ Ajustando ponderaciones basado en historial...")
        # Placeholder para lógica de aprendizaje avanzada

    def get_status_report(self):
        """Genera reporte del estado de todos los nodos"""
        report = {
            "timestamp": datetime.now().isoformat(),
            "total_nodes": len(self.nodes_data),
            "nodes": {}
        }

        for node_id, data in self.nodes_data.items():
            score = self.calculate_node_score(node_id, data)
            perf = self.performance_history.get(node_id, {})

            report["nodes"][node_id] = {
                "metrics": data,
                "score": round(score, 3),
                "performance": perf
            }

        return report


# === FUNCIONES DE CONFIGURACIÓN ===

def load_weights_from_file(filename="weights_config.json"):
    """Carga ponderaciones desde archivo JSON"""
    try:
        with open(filename, 'r') as f:
            return json.load(f)
    except FileNotFoundError:
        return None


def save_weights_to_file(weights, filename="weights_config.json"):
    """Guarda ponderaciones en archivo JSON"""
    with open(filename, 'w') as f:
        json.dump(weights, f, indent=4)


# === SERVIDOR FLASK INTEGRADO ===

app = Flask(__name__)
master = None  # Se inicializará en main


@app.route('/register', methods=['POST'])
def register_node():
    """Endpoint para registrar un nuevo nodo"""
    data = request.get_json()
    node_id = data.get('node_id')
    energy_watts = data.get('energy_watts', 100)

    if not node_id:
        return jsonify({"error": "node_id requerido"}), 400

    master.register_node(node_id, energy_watts)
    return jsonify({"status": "registered", "node_id": node_id}), 200


@app.route('/update_metrics', methods=['POST'])
def update_metrics():
    """Endpoint para recibir métricas de los nodos esclavos"""
    data = request.get_json()
    node_id = data.get('node_id') or request.remote_addr  # Usar IP si no hay ID

    # Extraer métricas
    metrics = {
        "cpu_cores": data.get("cpu_cores"),
        "cpu_percent": data.get("cpu_percent"),
        "ram_total_GB": data.get("ram_total_GB"),
        "ram_percent": data.get("ram_percent"),
        "cpu_temp": data.get("cpu_temp")
    }

    master.update_node_data(node_id, metrics)

    return jsonify({
        "status": "updated",
        "node_id": node_id,
        "timestamp": datetime.now().isoformat()
    }), 200


@app.route('/get_best_node', methods=['GET'])
def get_best_node():
    """Endpoint para obtener el mejor nodo disponible"""
    system_load = request.args.get('system_load', 'normal')

    best_node, score, all_scores = master.select_best_node(system_load)

    return jsonify({
        "best_node": best_node,
        "score": round(score, 3),
        "all_scores": {k: round(v, 3) for k, v in all_scores.items()},
        "timestamp": datetime.now().isoformat()
    }), 200


@app.route('/status', methods=['GET'])
def get_status():
    """Endpoint para obtener el estado completo del clúster"""
    return jsonify(master.get_status_report()), 200


@app.route('/update_performance', methods=['POST'])
def update_performance():
    """Endpoint para actualizar el rendimiento tras completar una tarea"""
    data = request.get_json()
    node_id = data.get('node_id')
    task_time = data.get('task_time')
    success = data.get('success', True)

    if not node_id or task_time is None:
        return jsonify({"error": "node_id y task_time requeridos"}), 400

    master.update_performance(node_id, task_time, success)

    return jsonify({"status": "performance_updated", "node_id": node_id}), 200


def monitor_loop():
    """Loop de monitorización que imprime el estado cada X segundos"""
    while True:
        time.sleep(30)  # Cada 30 segundos
        if master.nodes_data:
            print("\n" + "=" * 60)
            print(f"📊 ESTADO DEL CLÚSTER - {datetime.now().strftime('%H:%M:%S')}")
            print("=" * 60)

            for node_id, data in master.nodes_data.items():
                score = master.calculate_node_score(node_id, data)
                temp = data.get('cpu_temp', 'N/A')
                print(f"\n🖥️  {node_id}:")
                print(f"   CPU: {data.get('cpu_percent', 0):.1f}% | RAM: {data.get('ram_percent', 0):.1f}%")
                print(f"   Temp: {temp}°C | Score: {score:.3f}")

            print("\n" + "=" * 60)


# === EJEMPLO DE USO ===

if __name__ == "__main__":
    # Crear agente maestro con ponderaciones personalizadas
    custom_weights = {
        "cpu_availability": 0.35,
        "ram_availability": 0.30,
        "temperature": 0.15,
        "energy_efficiency": 0.15,
        "historical_performance": 0.05
    }

    master = MasterAgent(weights=custom_weights)

    # Cargar ponderaciones desde archivo si existe
    saved_weights = load_weights_from_file()
    if saved_weights:
        master.weights = saved_weights
        print("✅ Ponderaciones cargadas desde archivo")

    # Registrar nodos predefinidos (opcional)
    master.register_node("node_1", energy_watts=120)
    master.register_node("node_2", energy_watts=80)
    master.register_node("node_3", energy_watts=150)

    # Iniciar thread de monitorización
    monitor_thread = threading.Thread(target=monitor_loop, daemon=True)
    monitor_thread.start()

    print("\n🚀 Servidor maestro iniciado")
    print("📡 Esperando conexiones de nodos esclavos...")
    print(f"🌐 Endpoints disponibles:")
    print(f"   - POST /register          : Registrar nodo")
    print(f"   - POST /update_metrics    : Actualizar métricas")
    print(f"   - GET  /get_best_node     : Obtener mejor nodo")
    print(f"   - GET  /status            : Estado del clúster")
    print(f"   - POST /update_performance: Actualizar rendimiento\n")

    # Iniciar servidor Flask
    app.run(host='0.0.0.0', port=5000, debug=False)
