from flask_wtf import FlaskForm
from wtforms import SelectField, StringField, SubmitField, HiddenField, SelectMultipleField
from wtforms.validators import DataRequired, Optional

class ScanForm(FlaskForm):
    csrf_token = HiddenField()

    source_choice = SelectField(
        "Drive Source",
        choices=[
            ("1", "Array Only"),
            ("2", "Pools Only"),
            ("3", "Array + Pools"),
        ],
        validators=[DataRequired()],
    )

    drives = SelectMultipleField("Drives", choices=[], coerce=str, validators=[DataRequired()])
    min_size = StringField("Minimum File Size (MB)", validators=[Optional()])
    ext_filter = StringField("Extension Filter (e.g. .mkv,.mp4)", validators=[Optional()])

    strategy_choices = [
        ("newest", "Newest File"),
        ("oldest", "Oldest File"),
        ("largest", "Largest File"),
        ("smallest", "Smallest File"),
        ("most_space", "Drive with Most Free Space"),
        ("least_space", "Drive with Least Free Space"),
    ]

    keep_primary = SelectField(
        "Primary Keep Strategy",
        choices=strategy_choices,
        default="newest",  # Default to "newest"
        validators=[DataRequired()],
    )
    keep_tiebreaker1 = SelectField(
        "Secondary Preference",
        choices=strategy_choices,
        default="largest",  # Default to "Largest File"
        validators=[DataRequired()],
    )
    keep_tiebreaker2 = SelectField(
        "Tertiary Preference",
        choices=strategy_choices,
        default="least_space",  # Default to "Drive with Least Free Space"
        validators=[DataRequired()],
    )

    submit = SubmitField("Start Scan")