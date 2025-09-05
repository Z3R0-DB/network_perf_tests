def log_message(message):
    print(f"[LOG] {message}")

def format_results(results):
    return "\n".join(f"{key}: {value}" for key, value in results.items())

def save_to_file(filename, data):
    with open(filename, 'w') as file:
        file.write(data)

def load_from_file(filename):
    with open(filename, 'r') as file:
        return file.read()