from tools import combat_sweep as combat
from tools import env_matrix as env


def test_missing_actual_passage_cannot_pass():
    status, detail, _, _ = env.classify_result(
        'Bedroom', 'Bedroom', {'hasPassageNode': True, 'done': True, 'textLen': 5},
        timed_out=False,
    )
    assert status == 'hard_fail'
    assert 'actual passage missing' in detail


def test_unknown_combat_end_cannot_pass(monkeypatch):
    monkeypatch.setattr(combat, '_state', lambda page: {'combat': 0, 'passage': 'Bedroom'})
    result = combat.drive_combat(object(), path='win', max_rounds=80, timeout_ms=1000)
    assert result['outcome'] == 'unknown'
    assert result['verdict'] == 'soft_fail'
