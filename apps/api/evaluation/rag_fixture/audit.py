"""Synthetic audit storage interface."""


def append_event(store, actor_id, action, object_id):
    event = {"actor_id": actor_id, "action": action, "object_id": object_id}
    store.append(event)
    return event


def events_for_actor(store, actor_id):
    return [event for event in store if event["actor_id"] == actor_id]


def redact_event(event):
    return {key: value for key, value in event.items() if key != "client_email"}


def count_actions(store, action):
    return sum(event["action"] == action for event in store)
