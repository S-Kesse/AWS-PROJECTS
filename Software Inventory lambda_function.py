import os.path
import boto3
import email
import zipfile
from datetime import timedelta
from datetime import datetime
from datetime import date
from botocore.exceptions import ClientError
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.application import MIMEApplication

#account_list="""('788906687526','660212182825','022872522893','778111445197','136839026588','856723781721','895667335887')"""

def lambda_handler(event, context):
    #event process
    print('Trigger Event:')
    print(event)
    if 'LIST' in event:
        account_list=event['LIST']
        account_list=account_list.split(',')
        QUERY=f"""select * from aws_application where accountid in {account_list}"""
        QUERY=QUERY.replace("[","(")
        QUERY=QUERY.replace("]",")")
        print('Software Inventory input is AccountId list')
        print(f'Query: {QUERY}')
        report_prefix=event['NAME']
    elif 'OU' in event:
        org = boto3.client('organizations')
        ou=event['OU']
        ou_name=org.describe_organizational_unit(
            OrganizationalUnitId=ou
            )
        ou_name=ou_name['OrganizationalUnit']['Name']
        report_prefix=ou_name
        print('Software Inventory input is OrganizationalUnit')
        print(f'OU: {ou} {ou_name}')
        #get account id list
        account_list=[]
        response=org.list_accounts_for_parent(
            ParentId=ou
            )
        act_lst=response['Accounts']
        while "NextToken" in response:
            response=org.list_accounts_for_parent(
                ParentId=ou,
                NextToken=response["NextToken"]
                )
            act_lst.extend(response['Accounts'])
        for i in range(len(act_lst)):
            current_account=act_lst[i]['Id']
            account_list.append(current_account)
        act_sum=len(account_list)        
        print(f'Total accounts : {act_sum}') 
        QUERY=f"""select * from aws_application where accountid in {account_list}"""
        QUERY=QUERY.replace("[","(")
        QUERY=QUERY.replace("]",")")
        print(f'Query: {QUERY}')      
    else:
        print('Warning :  Please review the input event syntax')
        return('End of process')
    
    #Athena Query
    DATABASE = 'ssminventory'
    RESULT = 's3://org-894835236266-us-east-1-centralized-ssminventory-dev/athena/'
    athena = boto3.client('athena')
    response = athena.start_query_execution(
        QueryString=QUERY,
        QueryExecutionContext={
            'Database': DATABASE
        },
        ResultConfiguration={
            'OutputLocation': RESULT,
        }
    )

    
    #Waiting until query execution end
    QueryExecutionId=response['QueryExecutionId']
    print(f'Query Execution Id : {QueryExecutionId}')
    res = athena.get_query_execution(
        QueryExecutionId=QueryExecutionId
        )
    athena_exec_state = res['QueryExecution']['Status']['State']
    while (athena_exec_state == 'QUEUED' or athena_exec_state == 'RUNNING'):
        res = athena.get_query_execution(
            QueryExecutionId=QueryExecutionId
            )        
        athena_exec_state = res['QueryExecution']['Status']['State']
    print(f'Query execution state : {athena_exec_state}')
    
    #S3 processing download and upload results
    
    s3 = boto3.client('s3',region_name='us-east-1')
    BUCKET_NAME = 'org-894835236266-us-east-1-centralized-ssminventory-dev'
    s3_file_loc = res['QueryExecution']['ResultConfiguration']['OutputLocation']
    s3_file_key=s3_file_loc.replace("s3://"+BUCKET_NAME+"/","")
    dt=date.today()
    dtstr=dt.strftime("%Y%m%d")
    s3_new_filename=report_prefix+"_softwareinventory"+dtstr+".csv"
    
    s3.download_file(BUCKET_NAME, s3_file_key, "/tmp/"+s3_new_filename)
    
    s3_new_filename_upload="SoftwareInventory-Reports/"+report_prefix+"/"+s3_new_filename
    s3.upload_file("/tmp/"+s3_new_filename,BUCKET_NAME,s3_new_filename_upload)
    print(f"Uploaded to s3://{BUCKET_NAME}/{s3_new_filename_upload}")
    #ZIP file
    
    TMP_ZIP_FILE_NAME='/tmp/temp.zip'
    zf = zipfile.ZipFile(TMP_ZIP_FILE_NAME,mode='w',compression=zipfile.ZIP_DEFLATED)
    os.chdir('/tmp')
    zf.write(s3_new_filename)
    zf.close()    
    print('File compressed')
    #SES     
    ses = boto3.client('ses')
    tmp=date.today()
    datetoday=tmp.strftime("%m-%d-%Y")
    SENDER = "noreply@mitchell-aws.awsapps.com"
   
    #Building SES message headers then attachement
    RECIPIENT = event['EMAIL']
    SUBJECT = f"AWS Systems Manager - Software Inventory for {report_prefix} {datetoday}"
    BODY_TEXT = f"Please find attached the recent Software Inventory reports for {report_prefix} {datetoday}"
    msg = MIMEMultipart()
    msg['Subject'] = SUBJECT
    msg['From'] = SENDER
    msg['To'] = RECIPIENT
    textpart = MIMEText(BODY_TEXT)
    msg.attach(textpart)        
    ses_attached_file=report_prefix+"_softwareinventory"+dtstr+".zip"
    #attaching to mail
    ATTACHMENT = TMP_ZIP_FILE_NAME
    att = MIMEApplication(open(ATTACHMENT, 'rb').read())
    att.add_header('Content-Disposition','attachment',filename=ses_attached_file)
    msg.attach(att)
    print(f"File {ses_attached_file} attached")
              
     
    #sending email
    RECIPIENTS=RECIPIENT.split(",")
    try:
        response = ses.send_raw_email(
            Source=SENDER,
            Destinations=RECIPIENTS,
            RawMessage={ 'Data':msg.as_string() }
            )
    except ClientError as e:
        print(e.response['Error']['Message'])
    else:
        print(f"Email sent to {RECIPIENT}")
        print("Message ID:",response['MessageId'])
