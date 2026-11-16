# Snack Counter Automation - Design

## 1. Approach

Today nobody is responsible for a refill. The box stays empty because everyone assumes someone else will buy, and two people sometimes buy on the same day. After the purchase, nobody follows up on the HR claim.

The system makes one person responsible for each refill, picks that person fairly, and moves the job to someone else if they don't act. It also checks the budget before anyone buys and files the HR claim as soon as the receipt is uploaded.

All interaction happens through a bot in the existing chat tool: one channel per office plus direct messages. People don't need to install anything new.

## 2. Refill lifecycle

```
reported empty -> OFFERED -> COMMITTED -> CLAIM_SUBMITTED -> REIMBURSED
```

1. Report. Anyone can report an empty box in chat. If the office already has an open refill, the report is added to it instead of starting a new one.
2. Offer. The bot picks one volunteer (see section 4) and sends them a direct message with the budget limit. They have 2 hours to accept or decline. If they decline or don't answer, the bot asks the next person.
3. Commit. The first person to accept becomes the buyer, and the channel is told so nobody else buys. Anyone can accept, not only the person who was asked. The buyer's spending limit is reserved in the budget.
4. Purchase. The buyer has 24 hours to upload the receipt photo and the amount. If they miss the deadline, the refill is offered to the next person and the reserved budget is released.
5. Claim. Uploading the receipt creates the HR claim immediately. The bot checks the claim status every few minutes and closes the refill when HR approves it.

Other paths:

- Nobody available: the refill becomes OPEN. The channel is told that anyone can take it, and the bot tries again the next day.
- Budget used up: the refill becomes BLOCKED_BUDGET and the channel is told. It is offered again automatically at the start of the next month.
- Receipt above the limit: the refill becomes AWAITING_APPROVAL, and the claim is only sent after the office manager approves it.

## 3. Components and data

| Component | What it does | Data it keeps |
|---|---|---|
| Chat bot | Turns chat messages into commands and sends replies | Nothing |
| Refill service | Runs the lifecycle above | Refill: office, state, version number, offer and deadline, buyer, spending limit, amount, receipt, items, HR claim ID, history |
| Volunteer list | Who can be asked, and where they are on a given day | Volunteer: employee ID, home office, office days, holidays, visits to the other office |
| Office settings | Rules per office | Office: currency, time zone, monthly budget, typical purchase range, manager |
| Budget | Spent and remaining amounts per office and month | Nothing; calculated from the refills |
| Scheduler | Runs every few minutes: expired offers, missed deadlines, HR status | Nothing |
| Report | Monthly spending across both offices | Exchange rate per month |

The core logic only talks to the chat tool, the HR system and the clock through small interfaces. In the tests they are replaced by simulated versions, so a test can jump forward 24 hours instantly.

## 4. How each problem is handled

**Box sits empty.** Every step has one named person and a deadline. If they don't act, the job moves on automatically. If nobody is available, the whole channel is told.

**Two people buy on the same day.** An office can only have one open refill. Accepting uses a version number check, so if several people accept at the same moment, only one succeeds and the others are told who is buying.

**A few people do most refills.** The bot only asks people who are in that office today. It asks the person with the fewest refills in the last 60 days first; on a tie, the one whose last refill was longest ago.

**Slow reimbursement.** The claim is filed the moment the receipt is uploaded, so it no longer depends on the volunteer remembering to do it.

**Unknown spending.** Each buyer gets a spending limit: the remaining monthly budget, capped at the top of the typical purchase range. The monthly report shows each office in its own currency and a combined total in NOK.

**Which snacks get eaten.** Buyers list the items they bought, and the report shows the most bought items.

## 5. Assumptions

1. A visitor who refills the other office's box spends that office's budget, in that office's currency. HR converts it to their payroll currency.
2. The combined report is in NOK, using one fixed exchange rate per month. A purchase counts in the month of its local date in that office.
3. Spending above the limit needs the office manager's approval. When the budget runs out, the box waits for the next month.
4. The HR system returns a claim ID and we check its status by polling. "Approved" counts as reimbursed.
5. The chat tool has no presence information, so volunteers keep their office days, holidays and visits up to date.
6. People report an empty box themselves; there are no sensors.
7. Reimbursement through HR stays; a company card is out of scope.
8. The 2-hour and 24-hour time limits are settings and can be adjusted.

## 6. Trade-offs

- Asking one person is slightly slower than posting to the whole channel, but someone is clearly responsible. Anyone can still accept, so a person already at the shop can take it.
- The budget is calculated from the refills instead of being stored. This costs a small query each time, but the numbers can't get out of sync.
- Accepting is protected with a version check instead of locks. It works with any database.
- The bot polls HR instead of waiting for a webhook, because we don't know what the HR vendor supports. Claims take days, so polling every few minutes is enough.
- Deadlines run on normal time, so an offer sent in the evening can expire overnight. Pausing deadlines outside office hours would be the next improvement.

## 7. What I would not build

- Stock tracking per item. It needs effort from everyone, and the receipt items already show what is bought.
- Reading amounts from receipt photos. The buyer types the amount and HR checks the receipt anyway.
- A separate web app or dashboard. Chat and a monthly report cover what people need.
- Live exchange rates or payroll currency conversion. That is HR's and finance's job.
- Sensors or scales on the box. Too expensive and fragile for a snack box.
- A company card for each office. It may be the better long-term solution, but it is a policy decision, not software.

Left out of this version, but next in line: handling rejected HR claims, retrying when HR is unreachable, and reminding the manager about claims pending more than 10 days.
