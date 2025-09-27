# Agents (Python) — Time-Travel Inbox

## You own
- ADK/A2A orchestration (CanvasPoller → Scheduler/Prioritizer → Delivery)
- Pub/Sub topics: canvas.poll, schedule.tick, deliver.sms
- Firestore read/write (state, correlation ids)
- HTTP calls to teammates' services (Canvas, SMS)

## Start-of-hackathon TODO
- [ ] Create venv + install deps
- [ ] Implement `CanvasPollerAgent` (pull Node service → write Firestore → publish `canvas.poll`)
- [ ] Implement `SchedulerAgent` (subscribe `canvas.poll` + `schedule.tick` → compute windows → publish `deliver.sms`)
- [ ] Implement `DeliveryAgent` (subscribe `deliver.sms` → call SMS service)
- [ ] Add “DONE” handling (stop escalation on `schedule.tick` with status=done)
- [ ] Deploy to Cloud Run (single service is fine)

## Contracts folder
See `contracts/*.json` for Pub/Sub payload shapes.
