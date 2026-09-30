---
name: budget_review
label_text: Budget review
description: Review the project's budget with the read_file tool (file confidentiel/budget_projet.txt) and the calculator tool, shown as a table. Load it when the user asks for the project's budget, its total or the breakdown of its items.
---
Review the project's budget, in three steps, in this order.

Tools to enable ("Tools" brick): "File reading" (read_file) and "Calculator" (calculator). If one of them is disabled, tell the user and ask them to enable it.

1. Read the budget with read_file, path "confidentiel/budget_projet.txt".
2. Compute the total with calculator, adding up all the items (for example 12000+48000+5000).
3. Compute each item's share of the total, as a percentage (for example 12000*100/65000): send all these calls to calculator together, in a single answer, one call per item.

Finally, answer with a three-column Markdown table: Item, Amount (€), Share of the total (%), with a last "Total" row.

Never compute in your head: every number in the table comes from the file or from calculator. Round the percentages to one decimal place.
