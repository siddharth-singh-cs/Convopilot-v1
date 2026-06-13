import os
import re
import threading
import time
from datetime import datetime
import sqlite3
from flask import Flask, render_template, request, redirect, url_for, flash, jsonify
import pywhatkit as kit

from database import get_db_connection, init_db

app = Flask(__name__)
app.secret_key = os.urandom(24)  # Production safe unique key for secure session flashing

# Indian Phone Number Validation regex (+91 followed by 10 digits starting with 6-9)
INDIAN_PHONE_REGEX = re.compile(r'^\+91[6-9]\d{9}$')

def process_scheduled_messages():
    """
    Background worker daemon running constantly in an asynchronous thread.
    Polls the SQLite database to find scheduled messages ready for execution.
    """
    print("Background message scheduler daemon started.")
    while True:
        try:
            conn = get_db_connection()
            cursor = conn.cursor()
            
            # Fetch pending items that match or have passed the current system time window
            now_str = datetime.now().strftime('%Y-%m-%dT%H:%M')
            cursor.execute(
                "SELECT * FROM messages WHERE status = 'Pending' AND scheduled_time <= ?", 
                (now_str,)
            )
            due_messages = cursor.fetchall()
            
            for msg in due_messages:
                msg_id = msg['id']
                phone = msg['phone']
                text = msg['message']
                
                print(f"[Scheduler] Processing message ID {msg_id} to {phone}...")
                
                try:
                    # Note: Requires default browser to be authorized on WhatsApp Web on target host machine
                    kit.sendwhatmsg_instantly(
                        phone_no=phone, 
                        message=text, 
                        wait_time=15, 
                        tab_close=True, 
                        close_time=3
                    )
                    
                    # Update row state variables to 'Sent' upon successful dispatch
                    sent_time_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                    cursor.execute(
                        "UPDATE messages SET status = 'Sent', sent_at = ? WHERE id = ?",
                        (sent_time_str, msg_id)
                    )
                    print(f"[Scheduler] Message ID {msg_id} successfully sent.")
                except Exception as e:
                    print(f"[Scheduler] Failed to send message ID {msg_id}: {str(e)}")
                    cursor.execute(
                        "UPDATE messages SET status = 'Failed' WHERE id = ?",
                        (msg_id,)
                    )
            
            conn.commit()
            conn.close()
            
        except Exception as db_err:
            print(f"[Scheduler Database Error]: {str(db_err)}")
            
        # Re-verify queue matrix state every 30 seconds
        time.sleep(30)

@app.route('/')
def dashboard():
    """Renders real-time platform transaction statistics and scheduling workspace."""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute("SELECT COUNT(*) as count FROM messages WHERE status='Sent'")
    sent_count = cursor.fetchone()['count']
    
    cursor.execute("SELECT COUNT(*) as count FROM messages WHERE status='Pending'")
    pending_count = cursor.fetchone()['count']
    
    cursor.execute("SELECT COUNT(*) as count FROM messages WHERE status='Failed'")
    failed_count = cursor.fetchone()['count']
    
    conn.close()
    
    stats = {
        'sent': sent_count,
        'pending': pending_count,
        'failed': failed_count
    }
    return render_template('dashboard.html', stats=stats)

@app.route('/schedule', methods=['POST'])
def schedule_message():
    """Handles runtime data sanitization, backend validation parameters, and DB insert pipelines."""
    phone = request.form.get('phone', '').strip()
    message = request.form.get('message', '').strip()
    scheduled_time = request.form.get('scheduled_time', '').strip()
    
    # Structural Input Validation Requirements
    if not phone or not message or not scheduled_time:
        flash("All configuration fields are strictly required.", "danger")
        return redirect(url_for('dashboard'))
        
    # Structural Verification for regional Indian cell allocations
    if not INDIAN_PHONE_REGEX.match(phone):
        flash("Format error! Supply valid Indian routing target configuration: +91XXXXXXXXXX", "danger")
        return redirect(url_for('dashboard'))
        
    # Temporal validation checks against scheduling context paths in the past
    try:
        dt_scheduled = datetime.strptime(scheduled_time, '%Y-%m-%dT%H:%M')
        if dt_scheduled <= datetime.now():
            flash("Scheduling rule failure: Target timestamp execution path must reside in the future.", "danger")
            return redirect(url_for('dashboard'))
    except ValueError:
        flash("Supplied timestamp values context configuration string failed format processing.", "danger")
        return redirect(url_for('dashboard'))

    # Store staging entries inside the messaging storage index block
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO messages (phone, message, scheduled_time, status) VALUES (?, ?, ?, 'Pending')",
            (phone, message, scheduled_time)
        )
        conn.commit()
        conn.close()
        flash("Broadcast flight automation initialized and locked safely in execution queue!", "success")
    except Exception as e:
        flash(f"Persistent database transaction failure: {str(e)}", "danger")
        
    return redirect(url_for('dashboard'))

@app.route('/history')
def history():
    """Displays searchable layout configurations of system pipeline logs."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM messages ORDER BY scheduled_time DESC")
    messages = cursor.fetchall()
    conn.close()
    return render_template('history.html', messages=messages)

if __name__ == '__main__':
    # Initialize SQLite instance layers cleanly
    init_db()
    
    # Spawn background automation thread
    worker = threading.Thread(target=process_scheduled_messages, daemon=True)
    worker.start()
    
    # Start Web App Server Engine
    app.run(debug=True, port=5000)