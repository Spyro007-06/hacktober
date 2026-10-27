# Demo script (3 minutes)

Use offline mode (Gemma 4 E2B on Ollama) so the demo works with the WiFi off. If the real backend is not
available, the same flow runs on the frontend's mock backend (`npm run dev`); the mock triggers are listed
in [demo/README.md](../demo/README.md).

## Before you start

- Backend running (`uvicorn backend.main:app --port 8000`) and `python -m backend.provider_check` passes.
- Frontend running with `npm run dev:real`, opened on a phone or laptop with a microphone (HTTPS for a phone).
- A prepared photo of a broken streetlight and a second photo of garbage (for the mismatch moment).
- The status chip in the header shows **Offline**. Turn WiFi off now if you want to show it.

## The pitch (30 seconds)

"Residents don't know which office to write to, or how. Existing AI tools draft RTIs and send your data to
the cloud. Kural takes a Tamil voice complaint and a photo and produces the right document, with Gemma 4
running on this laptop. Gemma understands; fixed rules decide where it goes."

## Walkthrough

| Time | Do | Say |
|---|---|---|
| 0:30 | Open the landing page, then press **Start my complaint** | "Tamil is the default. Everything is also in English." |
| 0:45 | Record a 10 to 15 second Tamil complaint about a broken streetlight. Show the countdown and the transcript. Add the streetlight photo. Tap **Continue** | "Speech is transcribed locally. I review it before anything is analysed, because a wrong word could change the route." |
| 1:15 | Show the follow-up question (location) and answer it | "Gemma noticed the location was missing. The question is fixed text, and it never guesses." |
| 1:30 | On the route screen, point at the rule id and the reason | "The route comes from a rule table, not from Gemma. Here rule R2 fired, and you can see why." |
| 1:45 | Enter a name and address, tap **Generate draft** | "The department comes from a JSON table, and the wording from a template." |
| 2:00 | Scroll the bilingual document, tap **Edit** and change one sentence, then **Download PDF** | "Only Gemma-written text and personal details are editable. The legal wording is locked." |
| 2:20 | Play the next steps aloud (if a voice is configured), show the copy buttons for the portal fields | "These fields paste straight into the CM Helpline form." |
| 2:35 | **Mark as filed**, open **My complaints**, show the deadline | "It tracks the deadline, and when it is overdue one tap prepares the next step up the ladder." |

## The safety moment (optional, 30 seconds)

Start a new complaint, say "pothole", and attach the garbage photo. Gemma flags the mismatch before any
document is drafted. Then type "what a nice weather today" to show the "not a civic problem" screen.

## If something goes wrong

| Problem | Fallback |
|---|---|
| Microphone blocked | Type the complaint; typed input is always available |
| Model slow or offline model not loaded | Run `ollama run gemma4:e2b` once beforehand to warm it |
| No text-to-speech voice | The next steps stay on screen as text |
| PDF fails (Pango missing) | Show the on-screen document and the copy buttons |
| Real backend down | Switch the frontend to the mock backend (`npm run dev`) |
