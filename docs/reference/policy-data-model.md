From the policy document (AVB / Versicherungsschein)
Contract identity
Policy number, product name (e.g. "KFZ Komfort"), tariff generation/version of AKB
Underwriting insurer (relevant in white-label / fronting setups)
Broker / agent ID
Effective date, renewal date, cancellation status
Premium payment status (in arrears? — affects coverage under §38 VVG-equivalent rules)
Insured vehicle
License plate, VIN, make, model, first registration, engine power, fuel type
Vehicle value at inception, current sum insured (Kasko)
Use type: private / commercial / company car / rental / driving school / taxi
Annual mileage band declared
Garage address (often ≠ policyholder address; matters for parking-damage plausibility)
Modifications declared (tuning, retrofits)
Coverage scope
Liability sum (typically €100M combined in DE, but variants exist)
Kasko: Vollkasko / Teilkasko / none
Deductible per coverage line (Selbstbeteiligung Vollkasko, Teilkasko)
Add-ons: GAP, Neuwertentschädigung period, Mallorca-Police, Auslandsschadenschutz, Schutzbrief, Fahrerschutz, Insassenunfall, e-Bike, Ladeinfrastruktur (for EVs)
No-claims class (SF-Klasse) for liability and Vollkasko separately
Rabattretter / Rabattschutz: yes/no — huge impact on what the bot needs to disclose about SF-Rückstufung
Werkstattbindung tariff yes/no, and which network
Driver scope (Fahrerkreis)
Named drivers vs. open driver clause
Age restriction (e.g. "no driver under 23")
Youngest declared driver's date of birth
License-held-since date for declared drivers
Surcharge for occasional drivers declared
Geographic & temporal scope
Country coverage (typically EU + green-card states; some tariffs exclude specific countries)
Seasonal license plate (Saisonkennzeichen) months — critical: a claim outside the season window is uncovered
Short-term policies, transfer policies (Überführungskennzeichen)
Exclusions and special conditions
Race/track-day exclusion language
Gross negligence clause: fully waived / partially waived / standard
Telematics tariff conditions (and whether the device was active at time of loss)
Specific endorsements or individual agreements
Obligations (Obliegenheiten)
Reporting deadline (usually one week)
Police-notification requirements for specific loss types
Cooperation duties (witness info, document submission)
Repair authorization requirements before work starts (Vollkasko)
From the insurer database
Customer master data
Policyholder: full name, DOB, address, phone, email, preferred language, communication channel preferences
Bank details (for payouts — but never expose in chat)
Existing power-of-attorney / legal representative on file
Vulnerable-customer flags (where captured)
Consent status: marketing, telematics, data sharing with partners
Claims history
Prior claims on this policy: count, types, amounts, fault quotas, settlement status
Open claims (avoid duplicate FNOL — match incoming report against existing claim by date/location/vehicle)
Prior fraud flags or SIU referrals
Prior coverage denials and reasons
HIS (Hinweis- und Informationssystem) hits available at the carrier
Pre-existing damage records on the insured vehicle (from prior claims, inspections, or underwriting photos)
Vehicle data
Current mileage if telematics-equipped or last known from prior claim/inspection
Telematics trip data around the reported time of loss (massive validation lever — was the vehicle moving, where, how fast?)
Connected-car event data (airbag deployment, harsh braking, GPS at incident time) where available via OEM partnerships
Last HU/AU date if captured
Communication history
Prior conversations across channels (email, phone, portal, chat)
Open tasks or pending responses on other matters
Sentiment / NPS history if captured
