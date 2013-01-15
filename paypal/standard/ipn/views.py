#!/usr/bin/env python
# -*- coding: utf-8 -*-
import pytz
from django.http import HttpResponse
from django.contrib.auth.models import User
from mycroft.base.models import Access, Lecture

from django.views.decorators.http import require_POST
from django.views.decorators.csrf import csrf_exempt
from paypal.standard.ipn.forms import PayPalIPNForm
from paypal.standard.ipn.models import PayPalIPN
from datetime import datetime
from paypal.standard.ipn.signals import touch_user, license_user



@require_POST
@csrf_exempt
def ipn(request, item_check_callable=None):
    """
    PayPal IPN endpoint (notify_url).
    Used by both PayPal Payments Pro and Payments Standard to confirm transactions.
    http://tinyurl.com/d9vu9d
    
    PayPal IPN Simulator:
    https://developer.paypal.com/cgi-bin/devscr?cmd=_ipn-link-session
    """
    #TODO: Clean up code so that we don't need to set None here and have a lot
    #      of if checks just to determine if flag is set.
    flag = None
    ipn_obj = None
    # Clean up the data as PayPal sends some weird values such as "N/A"
    data = request.POST.copy()
    date_fields = ('time_created', 'payment_date', 'next_payment_date',
                   'subscr_date', 'subscr_effective')
    for date_field in date_fields:
        if data.get(date_field) == 'N/A':
            del data[date_field]

    data['payer_id'] = int(data['custom'])
      
    if data.get('txn_type') in ['web_accept','cart']:
        user = User.objects.get(pk=data['custom'])
        user.first_name = data['first_name']
        user.last_name = data['last_name']
        user.save()

    if data.get('txn_type') == 'web_accept':
        accessRecord = Access(user=user,lecture=Lecture.objects.get(pk=data['item_number']), 
            activation_date=datetime.now(pytz.utc),active=True)
        accessRecord.save()
        touch_user.send_robust(sender=data)

    elif data.get('txn_type') == 'cart':
        xname = []
        xnumber = []
        for x in xrange(int(data['num_cart_items'])):
            name = 'item_name' + str(x+1)
            xname.append(data[name])
            number = 'item_number' + str(x+1)
            xnumber.append(data[number])
            accessRecord = Access(user=User.objects.get(pk=data['custom']),lecture=Lecture.objects.get(pk=data[number]),activation_date=datetime.now(pytz.utc),active=True)
            accessRecord.save()
        data['item_name'] = ", ".join(xname)[:125]
        data['item_number'] = ", ".join(xnumber)
    
    elif data.get('txn_type') in ['subscr_signup']:
        license_user.send_robust(sender=data)

    elif data.get('txn_type') in ['subscr_payment']:
        pass
        
    form = PayPalIPNForm(data)
    if form.is_valid():
        try:
            #When commit = False, object is returned without saving to DB.
            ipn_obj = form.save(commit = False)
        except Exception, e:
            flag = "Exception while processing. (%s)" % e
    else:
        flag = "Invalid form. (%s)" % form.errors
 
    if ipn_obj is None:
        ipn_obj = PayPalIPN()
    
    #Set query params and sender's IP address
    ipn_obj.initialize(request)

    if flag is not None:
        #We save errors in the flag field
        ipn_obj.set_flag(flag)
    else:
        # Secrets should only be used over SSL.
        if request.is_secure() and 'secret' in request.GET:
            ipn_obj.verify_secret(form, request.GET['secret'])
        else:
            ipn_obj.verify(item_check_callable)

    ipn_obj.save()
    return HttpResponse("OKAY")
