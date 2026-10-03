"""A throwaway SMTP sink on 127.0.0.1:1025. Prints what it is handed.

Stands in for Gmail so the smtp code path can be proved without a credential —
the same role Mailpit plays in CI.
"""
import asyncio

from aiosmtpd.controller import Controller


class Sink:
    async def handle_DATA(self, server, session, envelope):
        text = envelope.content.decode("utf-8", "replace")
        subject = next((l for l in text.splitlines() if l.startswith("Subject:")), "(no subject)")
        has_link = "token=" in text
        print(f"DELIVERED to {envelope.rcpt_tos}: {subject} | carries a link: {has_link}", flush=True)
        return "250 OK"


controller = Controller(Sink(), hostname="127.0.0.1", port=1025)
controller.start()
print("sink listening on 127.0.0.1:1025", flush=True)
# The controller runs the server on its own thread; this just parks the main
# one so the process stays alive until Ctrl-C.
try:
    asyncio.run(asyncio.Event().wait())
except KeyboardInterrupt:
    controller.stop()
