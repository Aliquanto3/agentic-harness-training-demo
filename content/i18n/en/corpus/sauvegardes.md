# Exemplia backup policy

<!-- Fictitious text written for WaveStack. Exemplia is an imaginary organisation: this policy describes no real company. -->

Exemplia's data follows the 3-2-1 rule: at least 3 copies of each piece of data, on 2 different media, with 1 copy kept away from the main site. This rule applies to file servers, application databases and email.

The full backup of the servers takes place every Sunday at 2 am. Every weeknight, at 10 pm, an incremental backup copies only what has changed since the day before. Critical databases, such as accounting and customer management, are also backed up every 4 hours during the day.

Daily backups are kept for 35 days, weekly backups for 12 weeks, and one monthly backup is kept for 7 years for accounting obligations. A weekly copy is written to tape, then disconnected from the network and stored in a safe in a second building, 30 kilometres from headquarters: it stays out of reach of ransomware.

Recovery objectives are set per application. For critical applications, the maximum acceptable data loss is 4 hours and the service must be back up in under 8 hours. For other applications, the acceptable loss is 24 hours and the recovery time 2 working days.

A restore test is carried out every month on a sample of 10 randomly chosen files, and every six months on a complete application, in an isolated environment. The result of each test is recorded in the operations team's register; a failure is handled as a level 2 incident.

Workstations are not backed up: each employee saves their documents in their network space or in their team's space, which are. A file deleted by mistake can be restored by the support desk during the 35-day retention period, on simple request.
