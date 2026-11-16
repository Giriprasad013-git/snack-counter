# Snack Counter Automation

Take-home exercise for Framsikt: automating snack refills for the Oslo and Bengaluru offices.

The design document is in [docs/DESIGN.md](docs/DESIGN.md) (PDF: [docs/DESIGN.pdf](docs/DESIGN.pdf)).

## Running the tests

Python 3.10 or newer.

```bash
pip install -r requirements.txt
python -m pytest -v
```

`tzdata` is only needed on Windows, which has no built-in time zone data.

## Code

| File | Contents |
|---|---|
| `snack_counter/service.py` | The refill lifecycle: report, commit, decline, upload receipt, approve, and the scheduler `tick()` |
| `snack_counter/assignment.py` | Choosing who buys |
| `snack_counter/budget.py` | The budget check: spending limit and remaining budget per office |
| `snack_counter/models.py` | Office, Volunteer, Refill and the allowed state transitions |
| `snack_counter/report.py` | Monthly total across both offices |
| `snack_counter/money.py` | Money amounts and monthly exchange rates |
| `snack_counter/store.py` | In-memory storage with version checks |
| `snack_counter/ports.py`, `fakes.py` | Interfaces for chat, HR and the clock, and the simulated versions used in tests |

## Tests

| File | Rule |
|---|---|
| `test_commit_race.py` | Two people can't both commit to the same refill |
| `test_handover.py` | A refill nobody completes is handed to someone else |
| `test_budget.py` | Budgets are respected in each office's currency |
| `test_report.py` | Monthly totals are correct across both currencies |
| `test_assignment.py` | Only people in the office are asked, and the work is spread evenly |
| `test_lifecycle.py` | A refill goes from empty to reimbursed, one refill per office at a time |
| `test_money.py` | Money arithmetic and conversion |
