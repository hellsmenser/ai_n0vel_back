import json, random

def generate_scene():
    scene = {
        # ====== Метаинформация ======
        "id": "scene_debug_03",
        "name": "Разговор в лесу",
        "scene": random.choice(["bg_forest", "bg_tavern_interior"]),
        "music": "audio/forest_theme.ogg",
        "characters": {
            "lira": "Лира",
            "kael": "Каэль"
        },

        # ====== Контент ======
        "dialogue": []
    }

    dialogue_lines = [
        ("lira", "Ты опять молчишь. Думаешь, это спасёт нас?"),
        ("kael", "Слова не изменят того, что уже случилось."),
        ("lira", "Значит, будем просто ждать конца?"),
        ("kael", "Нет. Я ищу выход."),
        ("lira", "Выход? Из пепла и страха?"),
        ("kael", "Из нас самих."),
        ("lira", "Ты стал философом?"),
        ("kael", "Нет. Просто устал от крови."),
        ("lira", "Тогда, может, хоть раз скажи, что чувствуешь."),
        ("kael", "Лучше покажу делом.")
    ]

    emotions = {
        "lira": ["neutral", "sad", "angry", "smile"],
        "kael": ["neutral", "serious", "tired"]
    }

    inserts = [
        {
            "type": "pause",
            "duration": 1.2
        },
        {
            "type": "animate",
            "target": "lira",
            "effect": {
                "type": "shake",
                "xoffset": 10,
                "duration": 0.05,
                "repeat": 6
            }
        },
        {
            "type": "show",
            "target": "kael " + random.choice(emotions["kael"]),
            "transform": {
                "xalign": 0.8,
                "yalign": 0.0
            }
        },
        {
            "type": "show",
            "target": "lira " + random.choice(emotions["lira"]),
            "transform": {
                "xalign": 0.2,
                "yalign": 0.0
            }
        }
    ]

    scene["dialogue"].append(
        {
            "type": "show",
            "target": "lira " + random.choice(emotions["lira"]),
            "transform": {
                "xalign": 0.1,
                "yalign": 0.0
            }
        })
    scene["dialogue"].append(
        {
            "type": "show",
            "target": "kael " + random.choice(emotions["kael"]),
            "transform": {
                "xalign": 0.9,
                "yalign": 0.0,
                "flip": True
            }
        })

    for i, (actor, text) in enumerate(dialogue_lines):
        if random.random() < 0.4 and i > 0:
            scene["dialogue"].append(random.choice(inserts))
        scene["dialogue"].append({
            "type": "line",
            "speaker": actor,
            "text": text
        })

    # завершение сцены
    scene["dialogue"].append({
        "type": "transition",
        "effect": "fade"
    })
    scene["dialogue"].append({
        "type": "scene",
        "target": "bg campfire"
    })
    scene["dialogue"].append({
        "type": "music",
        "file": "audio/campfire.ogg",
        "fadein": 1.5,
        "loop": True
    })
    scene["dialogue"].append({
        "type": "jump",
        "target": "next_scene"
    })

    return scene


if __name__ == "__main__":
    print(json.dumps(generate_scene(), ensure_ascii=False, indent=4))
