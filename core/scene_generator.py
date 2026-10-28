"""Deterministic-shape demo data for the Ren'Py scene contract v1."""

import json
import random
from copy import deepcopy


BACKGROUND_IMAGES = ("bg_forest", "bg_tavern_interior")
CHARACTERS = {
    "lira": "Лира",
    "kael": "Каэль",
}
_UI_UNSET = object()


def generate_scene(scene_id="scene_debug_03", ui=_UI_UNSET):
    """Return a demo scene accepted by the Ren'Py JSON contract v1.

    This generator intentionally emits only assets and actions that the client
    currently has handlers for. Audio is omitted until the client gains a
    resource-backed music handler.
    """
    dialogue = [
        {
            "type": "scene",
            "target": random.choice(BACKGROUND_IMAGES),
        },
        {
            "type": "show",
            "target": "lira neutral",
            "transform": {"slot": "left", "yalign": 0.0},
        },
        {
            "type": "show",
            "target": "kael serious",
            "transform": {"slot": "right", "yalign": 0.0, "flip": True},
        },
    ]

    dialogue_lines = [
        ("lira", "Ты снова молчишь. Думаешь, это спасёт нас?"),
        ("kael", "Слова не изменят того, что уже случилось."),
        ("lira", "Значит, будем просто ждать конца?"),
        ("kael", "Нет. Я ищу выход."),
        ("lira", "Тогда покажи его делом."),
    ]

    for index, (speaker, text) in enumerate(dialogue_lines):
        if index == 2:
            dialogue.append(
                {
                    "type": "animate",
                    "target": "lira neutral",
                    "effect": {
                        "type": "shake",
                        "xoffset": 10,
                        "duration": 0.05,
                        "repeat": 3,
                    },
                }
            )
        if index == 4:
            dialogue.append({"type": "pause", "duration": 0.5})
        dialogue.append({"type": "line", "speaker": speaker, "text": text})

    dialogue.extend(
        [
            {"type": "transition", "effect": "fade"},
            {"type": "return"},
        ]
    )

    scene = {
        "schema_version": 1,
        "scene_id": str(scene_id),
        "name": "Разговор в лесу",
        "metadata": {"source": "orchestrator_demo"},
        "characters": dict(CHARACTERS),
        "dialogue": dialogue,
    }
    if ui is not _UI_UNSET:
        scene["ui"] = deepcopy(ui)
    return scene


if __name__ == "__main__":
    print(json.dumps(generate_scene(), ensure_ascii=False, indent=4))
