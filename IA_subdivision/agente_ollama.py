from flask import request, jsonify
from datetime import datetime  # ✅ CORREGIDO
import requests
from agente import MasterAgent, app

# ✅ Definir master como global
master = None


class MasterAgentWithOllama(MasterAgent):
    def __init__(self, weights=None, use_ollama=True, ollama_model='llama2'):
        super().__init__(weights)
        self.use_ollama = use_ollama
        self.ollama_model = ollama_model
        self.ollama_url = 'http://localhost:11434/api/generate'

    def query_ollama(self, prompt):
        """Consulta al modelo LLM local de Ollama"""
        try:
            payload = {
                'model': self.ollama_model,
                'prompt': prompt,
                'stream': False
            }
            response = requests.post(self.ollama_url, json=payload, timeout=30)
            if response.status_code == 200:
                return response.json().get('response', '')
            else:
                print(f"⚠️ Error en Ollama: {response.status_code}")
                return None
        except Exception as e:
            print(f"❌ No se pudo conectar a Ollama: {e}")
            return None

    def select_best_node_with_ollama(self, system_load="normal"):
        """Selecciona el mejor nodo usando Ollama + sistema de ponderaciones"""

        # 1. Calcular scores tradicionales primero
        scores_detail = {}
        for node_id, data in self.nodes_data.items():
            score = self.calculate_node_score(node_id, data, system_load)
            scores_detail[node_id] = score

        # 2. Si Ollama está habilitado, consultarlo
        if self.use_ollama and self.nodes_data:
            # Preparar prompt con información de los nodos
            prompt = self._build_ollama_prompt(scores_detail, system_load)

            ollama_response = self.query_ollama(prompt)

            if ollama_response:
                # Intentar extraer la recomendación de Ollama
                recommended_node = self._parse_ollama_response(ollama_response)

                if recommended_node and recommended_node in self.nodes_data:
                    print(f"🤖 Ollama recomienda: {recommended_node}")
                    print(f"   Razón: {ollama_response[:200]}...")

                    return recommended_node, scores_detail[recommended_node], scores_detail

        # 3. Fallback: usar el mejor score tradicional
        if scores_detail:  # ✅ Verificar que no esté vacío
            best_node = max(scores_detail, key=scores_detail.get)
            return best_node, scores_detail[best_node], scores_detail
        else:
            return None, 0, {}

    def _build_ollama_prompt(self, scores_detail, system_load):
        """Construye el prompt para Ollama con los datos de los nodos"""

        prompt = f"""Eres un experto en gestión de clústeres de computación. 
Necesito que selecciones el MEJOR nodo para ejecutar una tarea.

**Carga del sistema:** {system_load}

**Información de los nodos:**

"""

        for node_id, data in self.nodes_data.items():
            score = scores_detail.get(node_id, 0)
            perf = self.performance_history.get(node_id, {})

            prompt += f"""
**{node_id}:**
- CPU: {data.get('cpu_percent', 0):.1f}% usado ({data.get('cpu_cores', 0)} núcleos)
- RAM: {data.get('ram_percent', 0):.1f}% usado ({data.get('ram_total_GB', 0)} GB total)
- Temperatura: {data.get('cpu_temp', 'N/A')}°C
- Consumo energético: {self.energy_consumption.get(node_id, 100)}W
- Tareas completadas: {perf.get('tasks_completed', 0)}
- Tasa de éxito: {perf.get('success_rate', 0.5) * 100:.1f}%
- Puntuación calculada: {score:.3f}
"""

        prompt += """
**Instrucciones:**
1. Analiza los datos de cada nodo
2. Considera: disponibilidad de recursos, temperatura, eficiencia energética, historial
3. Responde SOLO con el nombre del nodo elegido (ejemplo: node_1) en la primera línea
4. En las siguientes líneas explica brevemente por qué

Tu respuesta:"""

        return prompt

    def _parse_ollama_response(self, response):
        """Extrae el nodo recomendado de la respuesta de Ollama"""
        # Buscar el nombre del nodo en la primera línea
        lines = response.strip().split('\n')
        if lines:
            first_line = lines[0].strip().lower()
            # Buscar coincidencias con los nodos conocidos
            for node_id in self.nodes_data.keys():
                if node_id.lower() in first_line:
                    return node_id
        return None


# === ENDPOINTS FLASK (solo si no existen en agente.py) ===

# ✅ Solo definir si agente.py NO tiene este endpoint
# Si ya existe, comenta o elimina esta función
@app.route('/request_task_ollama', methods=['POST'])  # ✅ Cambiado el nombre para evitar conflicto
def request_task_ollama():
    """Endpoint para que un esclavo pida una tarea (con Ollama)"""
    global master  # ✅ Declarar como global

    if master is None:
        return jsonify({"error": "Master no inicializado"}), 500

    data = request.get_json()
    node_id = data.get('node_id') or request.remote_addr

    # Verificar estado del nodo
    if node_id in master.nodes_data:
        score = master.calculate_node_score(node_id, master.nodes_data[node_id])
        if score < 0.3:
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


@app.route('/get_best_node_ollama', methods=['GET'])
def get_best_node_ollama():
    """Endpoint para consultar el mejor nodo usando Ollama"""
    global master  # ✅ Declarar como global

    if master is None:
        return jsonify({"error": "Master no inicializado"}), 500

    system_load = request.args.get('system_load', 'normal')

    if hasattr(master, 'select_best_node_with_ollama'):
        best_node, score, all_scores = master.select_best_node_with_ollama(system_load)
    else:
        return jsonify({"error": "Ollama no configurado"}), 500

    return jsonify({
        "best_node": best_node,
        "score": round(score, 3) if score else 0,
        "all_scores": {k: round(v, 3) for k, v in all_scores.items()},
        "method": "ollama+scoring",
        "timestamp": datetime.now().isoformat()  # ✅ Ahora funcionará
    }), 200


# === INICIALIZACIÓN ===

if __name__ == "__main__":
    custom_weights = {
        "cpu_availability": 0.35,
        "ram_availability": 0.30,
        "temperature": 0.15,
        "energy_efficiency": 0.15,
        "historical_performance": 0.05
    }

    # ✅ Asignar a la variable global
    master = MasterAgentWithOllama(
        weights=custom_weights,
        use_ollama=True,
        ollama_model='llama2'
    )

    # Añadir tareas de ejemplo
    master.add_task({"type": "train_model", "epochs": 10})
    master.add_task({"type": "process_data", "file": "data1.csv"})

    print("\n🚀 Servidor maestro con Ollama iniciado")
    print("🤖 Modelo: llama2")
    print("📡 Endpoints disponibles:")
    print("   - POST /request_task_ollama    : Pedir tarea (versión Ollama)")
    print("   - GET  /get_best_node_ollama   : Consultar mejor nodo con IA\n")

    app.run(host='0.0.0.0', port=5000, debug=False)
