"""Three new synthetic audit decks. Facts are fictional test inputs, not advice."""
import json
from pathlib import Path
import textwrap

from reportlab.pdfgen import canvas
from reportlab.lib.colors import HexColor

DECKS = {
    "library_pilot": [
        ("Booking", "Readers reserve one seat for 90 minutes. Unclaimed seats are released after 10 minutes."),
        ("Check-in", "A desk code confirms arrival. Staff use a paper register when the reader is offline."),
        ("Quiet room", "Calls take place outside the quiet room. Group discussions use the collaboration zone."),
        ("Book returns", "Returned books go into a separate tray. Staff scan each book before shelving it."),
        ("Overdue reminders", "A reminder is sent two days before the due date. A renewal is blocked when another reader reserved the book."),
        ("Device lending", "A laptop loan lasts four hours. Staff record the device condition at checkout and return."),
        ("Accessibility", "The pilot keeps two adjustable desks near the entrance. Readers can request large-print instructions."),
        ("Privacy", "Visit counts are stored without names. Booking details are removed after seven days."),
        ("Outage", "Staff record seat assignments on numbered cards during an outage. Cards are reconciled before the online schedule reopens."),
        ("Evaluation", "The team counts occupied seats every hour. Reader feedback is collected separately from booking records."),
    ],
    "repair_cafe": [
        ("Intake", "Visitors describe one fault per item. The intake volunteer records the item type and visible damage."),
        ("Triage", "Items with cracked power cables are isolated. Volunteers discuss other faults at the assessment desk."),
        ("Consent", "Visitors approve the proposed repair before work begins. A volunteer records any limits on the requested work."),
        ("Parts", "Spare parts are labeled by item type. An unavailable part is listed on a follow-up card."),
        ("Workstations", "Each workbench serves one repair at a time. Small loose parts stay in a numbered tray."),
        ("Buddy checks", "A second volunteer checks the repair notes before the item is returned. Unresolved issues are written on the return card."),
        ("Tool tracking", "Shared tools have numbered tags. A volunteer checks the tool board at the end of each session."),
        ("Visitor learning", "Visitors may observe the repair from the marked area. Volunteers explain the recorded fault after the work is complete."),
        ("Waste separation", "Removed batteries go into a dedicated collection box. Other replaced parts are sorted by material."),
        ("Pilot measures", "The pilot counts completed and unresolved repairs separately. Time spent waiting for parts is excluded from active repair time."),
    ],
    "campus_delivery": [
        ("Order windows", "The pilot accepts orders before noon. Orders received later are assigned to the next working day."),
        ("Pickup labels", "Each parcel receives a short pickup code. The public label excludes the recipient phone number."),
        ("Route planning", "The morning route visits three campus zones. A closed path is replaced by the signed accessible route."),
        ("Pickup confirmation", "The rider scans the parcel at pickup. An unreadable code is entered manually with a second check."),
        ("Handover", "The recipient provides the pickup code at handover. The rider records completion without taking a face photo."),
        ("Missed delivery", "A missed parcel returns to the service desk. The recipient receives a new pickup window."),
        ("Weather changes", "Heavy rain pauses the pilot route. The desk updates recipients before the route restarts."),
        ("Capacity", "A rider carries at most six parcels on one trip. Remaining parcels wait for the next scheduled trip."),
        ("Damaged packaging", "Damaged outer packaging is recorded before pickup. The desk confirms whether the parcel should continue."),
        ("Evaluation", "The team reports completed trips and missed deliveries separately. Waiting time at a closed path is recorded as a route delay."),
    ],
}


def build(output):
    output.mkdir(parents=True, exist_ok=True)
    manifest = dict(synthetic=True, fictional_facts=True, human_question_review_required=True, decks=[])
    for name, sections in DECKS.items():
        target = output / f"{name}.pdf"
        pdf = canvas.Canvas(str(target), pagesize=(960, 540))
        pdf.setTitle(name.replace("_", " "))
        pdf.setAuthor("")
        pdf.setCreator("")
        for number, (topic, facts) in enumerate(sections, 1):
            pdf.setFillColor(HexColor("#132e35"))
            pdf.rect(0, 0, 960, 540, fill=1, stroke=0)
            pdf.setFillColor(HexColor("#79e0b4"))
            pdf.setFont("Helvetica-Bold", 24)
            pdf.drawString(64, 450, topic)
            pdf.setFillColor(HexColor("#ffffff"))
            pdf.setFont("Helvetica", 24)
            y = 370
            for line in textwrap.wrap(facts, width=64):
                pdf.drawString(64, y, line)
                y -= 40
            pdf.showPage()
        pdf.save()
        manifest["decks"].append(dict(file=target.name, pages=[dict(page=i, topic=t, facts=f) for i, (t, f) in enumerate(sections, 1)]))
    (output / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    build(Path(__file__).resolve().parents[1] / "examples/question-audit")
