import psutil

def get_hardware_info():
    return {
        "cpu_cores": psutil.cpu_count(),
        "cpu_percent": psutil.cpu_percent(interval=1),  # Medido tras 1 segundo
        "ram_total_GB": round(psutil.virtual_memory().total / (1024 ** 3), 2),
        "ram_percent": psutil.virtual_memory().percent
    }


def get_cpu_temp_linux():
    # 1º Intenta método tradicional en SBC y portátiles
    try:
        with open("/sys/class/thermal/thermal_zone0/temp", "r") as f:
            temp_str = f.read()
            temp_c = int(temp_str) / 1000
            if temp_c > 0 and temp_c < 110:
                return temp_c
    except Exception:
        pass

    # 2º Intenta con psutil en PCs y servidores
    try:
        temps = psutil.sensors_temperatures()
        # Algunos equipos usan 'coretemp', otros 'k10temp', otros 'cpu_thermal'
        for key in ["coretemp", "k10temp", "cpu_thermal"]:
            if key in temps and temps[key]:
                # Retorna el valor medio de todos los sensores encontrados
                return round(sum([t.current for t in temps[key]]) / len(temps[key]), 1)
    except Exception:
        pass
    return None


def decide_node_assignment(info, cpu_temp, temp_threshold=75, ram_threshold=90):
    # No asignar carga si temperatura alta o RAM al límite
    if cpu_temp is not None and cpu_temp > temp_threshold:
        return "Nodo caliente, dejar enfriar"
    elif info["ram_percent"] > ram_threshold:
        return "RAM muy alta, asignar menos tareas"
    else:
        return "Nodo apto, puede recibir tareas"


if __name__ == "__main__":
    info = get_hardware_info()
    cpu_temp = get_cpu_temp_linux()

    print("Información hardware local:")
    print(f" - Núcleos CPU: {info['cpu_cores']}")
    print(f" - CPU usado (%): {info['cpu_percent']}")
    print(f" - RAM total (GB): {info['ram_total_GB']}")
    print(f" - RAM usada (%): {info['ram_percent']}")

    if cpu_temp is not None:
        print(f" - Temperatura CPU: {cpu_temp} °C")
        decision = decide_node_assignment(info, cpu_temp)
        print(f"\nDecisión de asignación: {decision}")
    else:
        print("Temperatura de CPU no disponible.")
