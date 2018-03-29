# vim:set shiftwidth=4 softtabstop=4 expandtab:
'''
Module: forms.maintenance.py

Created: 23.Mar.2018
Created by: Morten Hersson, <mhersson@gmail.com>
'''
from flask_wtf import FlaskForm
from wtforms import StringField, SelectField, SubmitField, HiddenField
from wtforms.validators import DataRequired, Regexp

from app import app


class ActivateForm(FlaskForm):
    key = SelectField(choices=app.config['MAINTENANCE_TAGS'])
    val = StringField(validators=[DataRequired()])
    duration = StringField(validators=[DataRequired(),
                                       Regexp("[1-9][0-9]*[m|h|d]")])
    submit = SubmitField('Activate')


class DeactivateForm(FlaskForm):
    start = HiddenField(validators=[DataRequired()])
    stop = HiddenField(validators=[DataRequired()])
    submit = SubmitField('Deactivate')
