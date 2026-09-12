# How to Contribute — in Plain Language

*No jargon here. If anything is still unclear after reading, that is a flaw in this text — tell us.*

Русская версия: [`PARTICIPATE.ru.md`](PARTICIPATE.ru.md)

---

## What this project is, in two sentences

We are building an AI that helps analyse tender and procurement documentation. Companies that bid on tenders need it: they have to read hundreds of pages of terms and extract the requirements from them.

We build it **in the open**. Whoever helps — with code, data, quality checks or computing time — has their contribution recorded in a public ledger. We all maintain that ledger together, and it cannot be changed retroactively.

If the project starts earning, revenue is shared among those who built it — in proportion to recorded contribution.

---

## Who can help

You do not have to be a programmer. Here are five ways.

### 1. Data — the most needed contribution

**What to do:** send examples of real documents and the correct answers to them. For instance: here is a passage of tender documentation, and here is the answer that should result from it.

**What matters:** these must be open documents or your own. You cannot send other people's copyrighted texts, or documents containing personal data — names, phone numbers, addresses.

**How long it takes:** from half an hour.

**How it is checked:** automatically. The program discards copies, checks whether our held-out set leaked into the data, and scans for personal data. What remains is counted.

### 2. Quality checks

**What to do:** find errors in how we measure model quality. For example: a question in the held-out set has two correct answers. Or the model answers correctly and our check fails to see it.

**Why this is valuable:** one error found in the evaluation system is worth more than a hundred new data examples. While the evaluation lies, we cannot tell whether the model got better or worse.

**How long it takes:** from an hour, and it needs a careful eye.

### 3. Code

**What to do:** ordinary tasks from the Issues list. PDF processing, document search, pipeline acceleration, bug fixes.

**How long it takes:** whatever works — from one evening.

### 4. Computing time

**What to do:** if you have access to a GPU, run our training or evaluation jobs on your own hardware and send back the result with proof.

**How long it takes:** a few hours of machine time, one command from you.

### 5. Model improvements

**What to do:** try a different fine-tuning approach, different settings, a different retrieval method — and show whether it got better.

**How it is checked:** only on our private held-out set. We do not show that set to anyone — otherwise people would start tuning against it, and it would stop meaning anything.

---

## How it works, step by step

**Step 1. You send the work.** Through an ordinary pull request — as in any open project.

**Step 2. The program checks it automatically.** No people, no discussion. The work either passes or it does not, and you see the reason immediately.

**Step 3. The contribution enters the ledger.** A public list recording who did what and when. Entries can be added; they cannot be changed or deleted.

**Step 4. Once a month, a snapshot of the ledger is published.** Everyone can see who contributed how much. The snapshot is additionally fixed with an external timestamp, so that not even we could alter it afterwards.

No applications, no forms, no approvals. You send it — it gets checked — it gets recorded.

---

## What you get

**Immediately:**

- **A record in the ledger.** It stays in the project's history forever and cannot be erased or rewritten.
- **Honest recognition of your contribution.** Public and verifiable: anyone can recompute the ledger from commit history and get the same result.
- **A working project in your portfolio.** Not a tutorial example, but a system with a real user.
- **Experience that is hard to get elsewhere:** measurable task definition, model quality evaluation, transparent contribution accounting.

**Later, if the project starts earning:**

- **Compensation** — proportional to recorded contribution. The mechanism appears together with revenue and a legal structure, not before.

---

## What you do NOT get — stated plainly

We wish every project wrote this down, so we will:

- **There is no money right now.** The project is at product stage; there is no revenue yet.
- **Points are not money.** They are a unit of accounting for your contribution. They cannot be sold, exchanged or transferred to another person.
- **We promise nothing.** No payments, no dates, no guarantee that a reward mechanism will ever appear. Promising a share in a project that has no revenue is fraud.
- **The project may shut down.** This is open development, not a guaranteed enterprise.

Why take part, then? Because this is a real project with a real task, not a demo. And because your contribution is recorded honestly — it will not be reassigned to you or to anyone else retroactively.

---

## Five rules to make sure your contribution counts

1. **One change, one commit.** Do not mix data, code and documentation in one edit: it is harder to verify.
2. **Data must be yours or open.** State where it comes from: a link and a licence.
3. **No personal data.** No names, phone numbers, addresses or document numbers. The check will find them, but better not to get there.
4. **Do not send the same thing twice.** Copies do not count: the program sees them.
5. **Sign your commits if you can.** This confirms the work is yours.

**If a contribution fails the check**, you will see the reason. Most often it is a duplicate or personal data — fixable in five minutes.

---

## Frequently asked questions

**I am not a programmer. Is there anything for me?**
Yes, and it is the most needed work: data and quality checks. No programming required — just attentiveness and domain understanding.

**How much time does it take?**
From half an hour, once. Regular participation is not required: contribute once and it is recorded.

**Will I be paid?**
Not now. If there are customers and revenue — yes, proportional to contribution. We do not name dates, because we do not want to promise things outside our control.

**Can I transfer or sell my points?**
No, and this rule is not up for discussion. Points belong to you personally and remain yours forever — but they are not a thing that can be sold.

**I am in another country. Can I take part?**
Yes. Geography does not matter. The one caveat: when it comes to payments, standard tax documentation and sanctions-list screening will be required — that is a legal requirement, not our preference.

**My contribution was rejected. What do I do?**
Look at the reason in the report. If you disagree, open a discussion; the decision is published with justification.

**Why do you record everything?**
So that a year from now, when the project is worth something, nobody has to argue about who did what. Recording it honestly now is far easier than untangling it later.

---

## First contribution in 15 minutes

1. Open **Issues** and find a task labelled `good first issue`.
2. If there is no data yet, take a task from the data section: document examples are needed there.
3. Fork the repository, add a file, open a pull request.
4. Wait for the automated check — it takes a couple of minutes, and the result appears in a comment.
5. A month later, find yourself in the ledger snapshot.

---

## Glossary

| Term | Meaning |
|---|---|
| **Contribution** | Any useful work: data, code, checks, computing time |
| **Points** | A unit of accounting for contribution. Not money, not sellable |
| **Ledger** | Public list of contributions. Append-only — cannot be rewritten |
| **Snapshot** | Monthly publication of the ledger: who contributed how much |
| **Anchor** | External timestamp fixing the snapshot so it cannot be substituted |
| **Held-out set** | Private set of examples used to measure model quality. Never published |
| **Validator** | Automated program that decides whether to accept a contribution |

---

*Ask questions in Issues with the `question` label. We answer all of them.*
