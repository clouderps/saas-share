# Tips default to 'on' (the current-screen hint shows without asking).
# 'quiet' was only ever the install default (introduced in 18.0.1.11.0 the
# same day), not a choice anyone made, so it moves to the new default.
def migrate(cr, version):
    cr.execute("UPDATE res_users SET ai_proactive_mode = 'on' WHERE ai_proactive_mode = 'quiet'")
