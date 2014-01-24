# -*- coding: utf-8 -*-
from __future__ import unicode_literals
import json

try:  # pragma: no cover
    from collections import OrderedDict
except ImportError:  # pragma: no cover
    from django.utils.datastructures import SortedDict as OrderedDict

from django.db import models
from django.template.defaultfilters import slugify
from django.utils.encoding import force_text, python_2_unicode_compatible
from django.utils.html import escape, mark_safe
from django.utils.translation import ugettext_lazy as _

from dynamic_forms.actions import action_registry
from dynamic_forms.conf import settings
from dynamic_forms.fields import TextMultiSelectField
from dynamic_forms.formfields import formfield_registry


@python_2_unicode_compatible
class FormModel(models.Model):
    name = models.CharField(_('Name'), max_length=50, unique=True)
    submit_url = models.CharField(_('Submit URL'), max_length=100, unique=True,
        help_text=mark_safe(_('The full URL path to the form. It should start '
            'and end with a forward slash (<code>/</code>).')))
    success_url = models.CharField(_('Success URL'), max_length=100,
        help_text=mark_safe(_('The full URL path where the user will be '
            'redirected after successfully sending the form. It should start '
            'and end with a forward slash (<code>/</code>). If empty, the '
            'success URL is generated by appending <code>done/</code> to the '
            '“Submit URL”.')), blank=True, default='')
    actions = TextMultiSelectField(_('Actions'), default='',
        choices=action_registry.get_as_choices())
    form_template = models.CharField(_('Form template path'), max_length=100,
        default='dynamic_forms/form.html',
        choices=settings.DYNAMIC_FORMS_FORM_TEMPLATES)
    success_template = models.CharField(_('Success template path'),
        max_length=100, default='dynamic_forms/form_success.html',
        choices=settings.DYNAMIC_FORMS_SUCCESS_TEMPLATES)

    class Meta:
        ordering = ['name']
        verbose_name = _('Dynamic form')
        verbose_name_plural = _('Dynamic forms')

    def __str__(self):
        return self.name

    def get_fields_as_dict(self):
        return OrderedDict(self.fields.values_list('name', 'label').all())

    def save(self, *args, **kwargs):
        """
        Makes sure that the ``submit_url`` and -- if defined the
        ``success_url`` -- end with a forward slash (``'/'``).
        """
        if not self.submit_url.endswith('/'):
            self.submit_url = self.submit_url + '/'
        if self.success_url:
            if not self.success_url.endswith('/'):
                self.success_url = self.success_url + '/'
        else:
            self.success_url = self.submit_url + 'done/'
        return super(FormModel, self).save(*args, **kwargs)


@python_2_unicode_compatible
class FormFieldModel(models.Model):

    parent_form = models.ForeignKey(FormModel, on_delete=models.CASCADE,
        related_name='fields')
    field_type = models.CharField(_('Type'), max_length=255,
        choices=formfield_registry.get_as_choices())
    label = models.CharField(_('Label'), max_length=20)
    name = models.SlugField(_('Name'), max_length=50, blank=True)
    _options = models.TextField(_('Options'), blank=True, null=True)
    position = models.SmallIntegerField(_('Position'), blank=True, default=0)

    class Meta:
        ordering = ['parent_form', 'position']
        unique_together = ("parent_form", "name",)
        verbose_name = _('Form field')
        verbose_name_plural = _('Form fields')

    def __str__(self):
        return _('Field “%(field_name)s” in form “%(form_name)s”') % {
            'field_name': self.label,
            'form_name': self.parent_form.name,
        }

    def generate_form_field(self, form):
        field_type_cls = formfield_registry.get(self.field_type)
        field = field_type_cls(**self.get_form_field_kwargs())
        field.contribute_to_form(form)
        return field

    def get_form_field_kwargs(self):
        kwargs = self.options
        kwargs.update({
            'name': self.name,
            'label': self.label,
        })
        return kwargs

    @property
    def options(self):
        """Options passed to the form field during construction."""
        if not hasattr(self, '_options_cached'):
            self._options_cached = {}
            if self._options:
                try:
                    self._options_cached = json.loads(self._options)
                except ValueError:
                    pass
        return self._options_cached

    @options.setter
    def options(self, opts):
        if hasattr(self, '_options_cached'):
            del self._options_cached
        self._options = json.dumps(opts)

    def save(self, *args, **kwargs):
        if not self.name:
            self.name = slugify(self.label)

        given_options = self.options
        field_type_cls = formfield_registry.get(self.field_type)
        invalid = set(self.options.keys()) - set(field_type_cls._meta.keys())
        if invalid:
            for key in invalid:
                del given_options[key]
            self.options = given_options

        return super(FormFieldModel, self).save(*args, **kwargs)


@python_2_unicode_compatible
class FormModelData(models.Model):
    form = models.ForeignKey(FormModel, on_delete=models.SET_NULL,
        related_name='data', null=True)
    value = models.TextField(_('Form data'), blank=True, default='')
    submitted = models.DateTimeField(_('Submitted on'), auto_now_add=True)

    class Meta:
        verbose_name = _('Form data')
        verbose_name_plural = _('Form data')

    def __str__(self):
        return _('Form: “%(form)s” on %(date)s') % {
            'form': self.form,
            'date': self.submitted,
        }

    def pretty_value(self):
        try:
            data = json.loads(self.value)
            output = ['<dl>']
            for k, v in sorted(data.items()):
                output.append('<dt>%(key)s</dt><dd>%(value)s</dd>' % {
                    'key': escape(force_text(k)),
                    'value': escape(force_text(v)),
                })
            output.append('</dl>')
            return mark_safe(''.join(output))
        except ValueError:
            return self.value
    pretty_value.allow_tags = True
