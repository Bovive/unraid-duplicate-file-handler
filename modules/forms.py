from flask_wtf import FlaskForm
from wtforms import SelectField, IntegerField, StringField, SubmitField, SelectMultipleField
from wtforms.validators import DataRequired, Optional
from wtforms.widgets import ListWidget, CheckboxInput

class ScanForm(FlaskForm):
    source_choice = SelectField(
        "Source Choice",
        choices=[
            ("1", "Array only"),
            ("2", "Pool only"),
            ("3", "Both Array and Pool"),
        ],
        validators=[DataRequired()],
    )
    drives = SelectMultipleField(
        "Select Drives",
        choices=[],  # Choices will be populated dynamically
        validators=[Optional()],
        coerce=str,
        widget=ListWidget(prefix_label=False),  # Render as a list
        option_widget=CheckboxInput(),         # Render each option as a checkbox
    )
    min_size = IntegerField(
        "Minimum File Size (bytes)", validators=[Optional()]
    )
    ext_filter = StringField(
        "File Extensions (comma-separated)", validators=[Optional()]
    )
    keep_strategy = SelectField(
        "Keep Strategy",
        choices=[
            ("newest", "Newest"),
            ("oldest", "Oldest"),
            ("largest", "Largest"),
            ("smallest", "Smallest"),
        ],
        validators=[DataRequired()],
    )
    submit = SubmitField("Start Scan")
