# vim:set shiftwidth=4 softtabstop=4 expandtab:
# pylint: disable=R0903
'''
Module: forms.maintenance.py

Created: 23.Mar.2018
Created by: Morten Hersson, <mhersson@gmail.com>
'''
from flask_wtf import FlaskForm
from wtforms import StringField, SelectField, SubmitField, HiddenField
from wtforms import SelectMultipleField, widgets
from wtforms.validators import DataRequired, Regexp, Optional

from app import app


class MultiCheckboxField(SelectMultipleField):
    widget = widgets.ListWidget(prefix_label=True)
    option_widget = widgets.CheckboxInput()


class ActivateForm(FlaskForm):
    key = SelectField(choices=app.config['MAINTENANCE_TAGS'])
    val = StringField(validators=[DataRequired()])
    duration = StringField(validators=[DataRequired(),
                                       Regexp("[1-9][0-9]*[m|h|d|w]")])
    days = MultiCheckboxField(validators=[Optional()],
                              choices=[("0", "Mon"), ("1", "Tue"),
                                       ("2", "Wed"), ("3", "Thu"),
                                       ("4", "Fri"), ("5", "Sat"),
                                       ("6", "Sun")])
    starttime = StringField(validators=[
        Optional(), Regexp("[0-2]{,1}[0-9]:[0-5][0-9]")])
    repeat = MultiCheckboxField(validators=[Optional()],
                                choices=[("1", "Repeat")])
    submit = SubmitField('Activate')


class DeactivateForm(FlaskForm):
    key = HiddenField(validators=[DataRequired()])
    value = HiddenField(validators=[DataRequired()])
    start = HiddenField(validators=[DataRequired()])
    stop = HiddenField(validators=[DataRequired()])
    submit = SubmitField('Deactivate')


class DeleteSchedule(FlaskForm):
    schedule_id = HiddenField(validators=[DataRequired()])
    submit = SubmitField('Delete')
