# Demo complaints

Recordings and photos are not stored in the repository (`*.wav`, `*.webm` and `*.m4a` are git-ignored, to keep
personal data out). Record each complaint yourself on the day, or type the text; the expected result is the same.
Put your own files in `demo/audio/` and `demo/photos/` if you want to keep them locally.

## Scenarios and expected results

The routes come from the rule table in `backend/data/rules.json`, so they are the same every time.

| # | Say or type | Photo | Expected result |
|---|---|---|---|
| 1 | "The streetlight on Gandhi Street has not worked for three weeks." / "காந்தி தெருவில் தெருவிளக்கு மூன்று வாரங்களாக எரியவில்லை." | A broken or dark streetlight | Ready; **R2**, local body complaint |
| 2 | "There is a big pothole in front of my house." | A photo of garbage | **Photo mismatch** screen: retake, or continue anyway |
| 3 | "The road near the market is full of water." (no street named) | None | One **follow-up question** for the location, then ready |
| 4 | "I want the records of the money spent on repairing our street in the last two years." | None | Ready; **R1**, RTI application |
| 5 | "I complained about the garbage on my street two months ago and nobody came." | A garbage photo | Ready; **R3**, CM Helpline grievance (when an earlier complaint is on record or the citizen says it was ignored) |
| 6 | "What a nice weather today." | None | **Not a civic problem** screen (R5); no document |
| 7 | An overdue CM Helpline complaint at its last level | | Escalation prepares an RTI asking for the action taken (**R4**) |

## Mock backend triggers

With `npm run dev` (no backend), the frontend's mock backend reacts to the complaint text:

| Text contains | Result |
|---|---|
| `weather` or `movie` | Not a civic problem |
| `pothole` and at least one photo | Photo mismatch |
| `fail` | A model timeout error, to show the retry |
| anything else | One follow-up question (location), then CM Helpline, rule R3 |

## Tips for a smooth recording

- Speak one or two sentences, about 10 to 15 seconds, in a quiet room.
- Check the transcript on screen and correct any wrong word before pressing Continue.
- Keep one photo per scenario small and in good light; the app resizes photos before the model sees them.
