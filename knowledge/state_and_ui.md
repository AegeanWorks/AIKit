# State Management & Presentation Layer

## 🎨 Presentation Architecture
Not applicable to AIKit: it has no graphical or web interface. Its presentation layer is each CLI's argument parsing and terminal output, described in `services.md` and `README.md`.

## 🔄 State Lifecycle
AIKit's only state file is `.agents/task_ledger.json` (schema in `data_models.md`).
1. **Load**: parse, quarantine a corrupt file, fall back to `.bak`, migrate the schema (**PRINCIPLE-013** R4).
2. **Change**: every read-modify-write holds the advisory lock (**PRINCIPLE-013** R3).
3. **Write**: headroom check, temp file, fsync, retried `os.replace`, directory fsync (**PRINCIPLE-013** R1, R2).
4. **Resume**: `disruption_recovery.py --resume` reports the active task, its plan and the phase to continue (**PRINCIPLE-004** R2).
