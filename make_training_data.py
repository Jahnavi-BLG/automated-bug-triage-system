"""Generates data/training.csv - the labelled bug reports used to train the classifiers.
Run:  python make_training_data.py      (already run once; re-run to regenerate)"""
import csv, random, os
random.seed(7)
OBJECTS = {
 "ui": ["dashboard page","dropdown menu","navigation bar","settings form","profile page","search box","sidebar","modal dialog","mobile layout","footer links","login button","submit button"],
 "backend": ["REST API","order service","report export","email service","file upload","background job","webhook handler","user service","search endpoint","notification service"],
 "database": ["customer table","database migration","SQL query","stored procedure","database connection","orders index","backup job","data sync","audit log table","reporting query"],
 "payments": ["payment page","checkout","refund flow","card transaction","invoice generation","UPI payment","payment gateway","billing page","coupon code","wallet balance"],
 "auth": ["login","password reset","OTP verification","session token","user permissions","single sign-on","access control","two-factor authentication","JWT token","admin role"],
}
# (type, severity, phrase)
SYMPTOMS = [
 *[("Bug","Critical",p) for p in ["crashes on startup","crashes when I click it","causes data loss","is completely down","throws a fatal error and nothing works","corrupts saved data"]],
 *[("Bug","High",p) for p in ["returns a 500 error","fails with an exception","does not work for many users","shows wrong results","stops responding","fails intermittently"]],
 *[("Bug","Medium",p) for p in ["shows an incorrect value sometimes","behaves inconsistently","does not refresh after an update","displays a wrong message","ignores the selected option","is not working properly","button does nothing when clicked"]],
 *[("Bug","Low",p) for p in ["has a small visual glitch","has a typo in the text","is slightly misaligned","uses the wrong colour","has an extra blank space"]],
 *[("Performance","Medium",p) for p in ["loads very slowly","is slow under heavy load","uses too much memory","lags when scrolling","is very slow","takes forever to load","hangs for a long time"]],
 *[("Performance","High",p) for p in ["times out for large data","takes more than 30 seconds to respond"]],
 *[("Security","Critical",p) for p in ["is vulnerable to SQL injection","exposes user data publicly","allows access without a password","leaks sensitive tokens in the logs"]],
 *[("Security","High",p) for p in ["has no rate limiting","stores passwords in plain text"]],
 *[("Feature Request","Low",p) for p in ["needs support for dark mode","should allow exporting to CSV","would be better with a bulk edit option","needs an option to filter by date"]],
]
TEMPLATES = ["{O} {s}","The {o} {s} after the latest release","Users report that the {o} {s}","{O} {s}. Steps: open the app and try again","Problem: the {o} {s} on production"]
rows=[]
for comp, objs in OBJECTS.items():
    for obj in objs:
        for typ, sev, ph in random.sample(SYMPTOMS, 14):
            t=random.choice(TEMPLATES).format(O=obj[0].upper()+obj[1:], o=obj, s=ph)
            rows.append((t,typ,sev,comp))
os.makedirs("data",exist_ok=True)
with open("data/training.csv","w",newline="",encoding="utf-8") as f:
    w=csv.writer(f); w.writerow(["text","type","severity","component"]); w.writerows(rows)
print(len(rows),"rows written to data/training.csv")
