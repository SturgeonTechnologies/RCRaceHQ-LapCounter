# Walk-up check-in

Racers at the track join the hotspot, land on the live page (the captive
portal sends them to `/`), tap **Racing today? Check in here**, type their
phone number and press **I'm here**.

- **Open only on race day:** the page works once an event is checked out on
  this Pi (Events → event → Check out). Before that it says check-in isn't open.
- **Which number:** the phone on the racer's RC Race HQ account, or on the
  account that registered them (a parent). One number checks in every
  registration it matches in that event.
- **What they see:** their first name, their classes and a to-do list. Nothing
  else from the registration.
  - "Bring your car to the learning table" when the transponder is missing or
    not learned on this Pi.
  - The staff note from the event page (for example "Tech inspection at the
    tower"). One note per Pi, shown for every racer.
- **Staff view:** the event page shows how many registrations are checked in
  and who isn't here yet.
- **RC Race HQ:** each new check-in queues `entry.checkin`
  (`{registrationId, atMs}`); RC Race HQ stores `checkedInAt` on the
  registration. A second check-in queues nothing.

## Privacy

The Pi never stores phone numbers. Each pack entry carries `firstName` and
`phoneTags`: `sha256("rchq-checkin:<eventId>:<E.164>")`, first 32 hex
characters, for the racer's and the purchaser's account phones. The typed
number is normalized the same way as RC Race HQ (`lib/phone.ts`) and hashed.

A phone number has few enough possibilities that a tag can be brute-forced by
someone who has the pack, so this keeps numbers out of the pack and off the
SD card, not out of reach of a determined attacker with the Pi.

The hotspot is open, so anyone on it can type any number. Tries are limited to
6 a minute per device and 60 a minute overall, and a match shows only a first
name and classes. A texted code can be added once SMS is live.
