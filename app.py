import os
import time
import logging
from datetime import datetime
from flask import Flask, render_template, request, redirect, url_for, Response, flash, Markup, jsonify
import cv2
import face_recognition
import numpy as np
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.exc import IntegrityError
from openpyxl import Workbook
from io import BytesIO
from flask import session
# Add this import at the top
from datetime import datetime, timedelta
from openpyxl import Workbook
from io import BytesIO



# Initialize logging
logging.basicConfig(level=logging.DEBUG)

app = Flask(__name__)
app.secret_key = 'NkosinathiSecretKey'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + os.path.join(os.path.abspath(os.path.dirname(__file__)), 'attendance.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

class Student(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.String(20), unique=True, nullable=False)
    name = db.Column(db.String(100), nullable=False)
    faculty = db.Column(db.String(50))
    course = db.Column(db.String(50))
    email = db.Column(db.String(100))
    phone = db.Column(db.String(20))
    password = db.Column(db.String(100), nullable=False)  # Add this line
    date_registered = db.Column(db.DateTime, default=datetime.utcnow)

class Attendance(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.String(20), nullable=False)
    name = db.Column(db.String(100), nullable=False)
    module = db.Column(db.String(100))
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    

class Lecturer(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    surname = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(100), unique=True, nullable=False)
    faculty = db.Column(db.String(50), nullable=False)
    password = db.Column(db.String(100), nullable=False)
    date_registered = db.Column(db.DateTime, default=datetime.utcnow)

class Module(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    faculty = db.Column(db.String(50), nullable=False)
    start_time = db.Column(db.Time, nullable=False)
    end_time = db.Column(db.Time, nullable=False)
    day_of_week = db.Column(db.Integer, nullable=False)  # 0=Monday, 6=Sunday
    lecturer_id = db.Column(db.Integer, db.ForeignKey('lecturer.id'), nullable=False)
    date_created = db.Column(db.DateTime, default=datetime.utcnow)
    
    lecturer = db.relationship('Lecturer', backref='modules')

# Faculty and course data
FACULTIES = {
    "Accounting and Informatics": [
        "Diploma in Accounting",
        "Diploma in ICT APP DEV",
        "Diploma of ICT BA",
        "Bachelor of ICT"
    ],
    "Engineering": [
        "Diploma in Civil Engineering",
        "Diploma in Electrical Engineering",
        "Bachelor of Engineering Technology"
    ],
    "Health Sciences": [
        "Diploma in Nursing",
        "Diploma in Emergency Medical Care",
        "Bachelor of Health Sciences"
    ],
    "Management Sciences": [
        "Diploma in Business Management",
        "Diploma in Marketing",
        "Bachelor of Business Administration"
    ]
}



with app.app_context():
   
    db.create_all()
    os.makedirs('static/encodings', exist_ok=True)

    # Add some sample modules if needed
    if not Module.query.first():
        sample_lecturer = Lecturer(
            name="Admin",
            surname="User",
            email="admin@dut.ac.za",
            faculty="Accounting and Informatics",
            password="admin123"
        )
        db.session.add(sample_lecturer)
        db.session.commit()
        
        sample_modules = [
            Module(name="Introduction to Programming", faculty="Accounting and Informatics", 
                  start_time=datetime.strptime("08:00", "%H:%M").time(), 
                  end_time=datetime.strptime("10:00", "%H:%M").time(),
                  day_of_week=0,  # Monday
                  lecturer_id=sample_lecturer.id),
            Module(name="Database Systems", faculty="Accounting and Informatics",
                  start_time=datetime.strptime("10:00", "%H:%M").time(),
                  end_time=datetime.strptime("12:00", "%H:%M").time(),
                  day_of_week=2,  # Wednesday
                  lecturer_id=sample_lecturer.id)
        ]
        db.session.add_all(sample_modules)
        db.session.commit()

def gen_frames():
    cap = cv2.VideoCapture(0)
    while True:
        success, frame = cap.read()
        if not success:
            break
        ret, buffer = cv2.imencode('.jpg', frame)
        frame = buffer.tobytes()
        yield (b'--frame\r\n'
               b'Content-Type: image/jpeg\r\n\r\n' + frame + b'\r\n')

@app.route('/')
def home():
    student_count = Student.query.count()
    today_attendance = Attendance.query.filter(
        db.func.date(Attendance.timestamp) == datetime.today().date()
    ).count()
    recent_attendance = Attendance.query.order_by(Attendance.timestamp.desc()).limit(5).all()
    
    return render_template(
        'home.html',
        student_count=student_count,
        today_attendance=today_attendance,
        recent_attendance=recent_attendance
    )

@app.route('/add_module', methods=['GET', 'POST'])
def add_module():
    if 'lecturer_id' not in session:
        flash('Please login first', 'error')
        return redirect(url_for('login_lecturer'))
    
    lecturer = Lecturer.query.get(session['lecturer_id'])
    if not lecturer:
        session.clear()
        flash('Lecturer not found', 'error')
        return redirect(url_for('login_lecturer'))
    
    # Define days of the week
    days_of_week = [
        (0, 'Monday'),
        (1, 'Tuesday'),
        (2, 'Wednesday'),
        (3, 'Thursday'),
        (4, 'Friday'),
        (5, 'Saturday'),
        (6, 'Sunday')
    ]
    
    if request.method == 'POST':
        name = request.form['name'].strip()
        start_time = request.form['start_time'].strip()
        end_time = request.form['end_time'].strip()
        day_of_week = int(request.form['day_of_week'])
        
        try:
            start_time = datetime.strptime(start_time, "%H:%M").time()
            end_time = datetime.strptime(end_time, "%H:%M").time()
            
            if start_time >= end_time:
                flash('End time must be after start time', 'error')
                return render_template('add_module.html', 
                                     faculties=FACULTIES,
                                     days_of_week=days_of_week)
            
            new_module = Module(
                name=name,
                faculty=lecturer.faculty,
                start_time=start_time,
                end_time=end_time,
                day_of_week=day_of_week,
                lecturer_id=lecturer.id
            )
            db.session.add(new_module)
            db.session.commit()
            flash('Module added successfully!', 'success')
            return redirect(url_for('lecturer_dashboard'))
        except ValueError:
            flash('Invalid time format. Please use HH:MM', 'error')
        except Exception as e:
            db.session.rollback()
            flash(f'Error adding module: {str(e)}', 'error')
    
    return render_template('add_module.html', 
                         faculties=FACULTIES,
                         days_of_week=days_of_week)

@app.route('/modules')
def list_modules():
    if 'lecturer_id' not in session:
        flash('Please login first', 'error')
        return redirect(url_for('login_lecturer'))
    
    lecturer = Lecturer.query.get(session['lecturer_id'])
    if not lecturer:
        session.clear()
        flash('Lecturer not found', 'error')
        return redirect(url_for('login_lecturer'))
    
    modules = Module.query.filter_by(faculty=lecturer.faculty).all()
    return render_template('modules.html', modules=modules)

@app.route('/delete_module/<int:module_id>', methods=['POST'])
def delete_module(module_id):
    if 'lecturer_id' not in session:
        flash('Please login first', 'error')
        return redirect(url_for('login_lecturer'))
    
    module = Module.query.get_or_404(module_id)
    if module.lecturer_id != session['lecturer_id']:
        flash('You can only delete your own modules', 'error')
        return redirect(url_for('list_modules'))
    
    try:
        db.session.delete(module)
        db.session.commit()
        flash('Module deleted successfully!', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error deleting module: {str(e)}', 'error')
    
    return redirect(url_for('list_modules'))

@app.route('/register_lecturer', methods=['GET', 'POST'])
def register_lecturer():
    if request.method == 'POST':
        name = request.form['name'].strip()
        surname = request.form['surname'].strip()
        email = request.form['email'].strip().lower()
        faculty = request.form.get('faculty', '').strip()
        password = request.form['password'].strip()
        confirm_password = request.form['confirm_password'].strip()

        # Validation
        errors = []
        if not email.endswith('@dut.ac.za'):
            errors.append("Email must end with @dut.ac.za")
        if password != confirm_password:
            errors.append("Passwords do not match")
        if len(password) < 8:
            errors.append("Password must be at least 8 characters")
            
        if errors:
            for error in errors:
                flash(error, 'error')
            return render_template('register_lecturer.html', 
                                faculties=FACULTIES,
                                selected_faculty=faculty)

        if Lecturer.query.filter_by(email=email).first():
            flash('Email already exists!', 'error')
            return render_template('register_lecturer.html', 
                                faculties=FACULTIES,
                                selected_faculty=faculty)

        try:
            new_lecturer = Lecturer(
                name=name,
                surname=surname,
                email=email,
                faculty=faculty,
                password=password  # In production, you should hash this password
            )
            db.session.add(new_lecturer)
            db.session.commit()
            flash('Lecturer registered successfully!', 'success')
            return redirect(url_for('login_lecturer'))
        except Exception as e:
            db.session.rollback()
            flash(f'Registration failed: {str(e)}', 'error')
    
    return render_template('register_lecturer.html', 
                         faculties=FACULTIES,
                         selected_faculty=None)

@app.route('/login_lecturer', methods=['GET', 'POST'])
def login_lecturer():
    if request.method == 'POST':
        email = request.form['email'].strip().lower()
        password = request.form['password'].strip()

        lecturer = Lecturer.query.filter_by(email=email).first()
        
        if not lecturer:
            flash('Invalid email or password', 'error')
            return redirect(url_for('login_lecturer'))
            
        if lecturer.password != password:  # In production, use password hashing
            flash('Invalid email or password', 'error')
            return redirect(url_for('login_lecturer'))
            
        # Store lecturer info in session
        session['lecturer_id'] = lecturer.id
        session['lecturer_name'] = lecturer.name
        session['lecturer_faculty'] = lecturer.faculty
        
        # Count students in the same faculty
        student_count = Student.query.filter_by(faculty=lecturer.faculty).count()
        #flash(f'Welcome back, {lecturer.name}! There are {student_count} students registered in your faculty.', 'success')
        return redirect(url_for('lecturer_dashboard'))
    
    return render_template('login_lecturer.html')

@app.route('/lecturer_dashboard')
def lecturer_dashboard():
    if 'lecturer_id' not in session:
        flash('Please login first', 'error')
        return redirect(url_for('login_lecturer'))
    
    lecturer = Lecturer.query.get(session['lecturer_id'])
    if not lecturer:
        session.clear()
        flash('Lecturer not found', 'error')
        return redirect(url_for('login_lecturer'))
    
    # Get statistics
    student_count = Student.query.filter_by(faculty=lecturer.faculty).count()
    today = datetime.now().date()
    
    faculty_modules = Module.query.filter_by(faculty=lecturer.faculty).all()
    module_names = [m.name for m in faculty_modules]
    
    today_attendance = Attendance.query.filter(
        db.func.date(Attendance.timestamp) == today,
        Attendance.module.in_(module_names)
    ).count()
    
    recent_attendance = Attendance.query.filter(
        Attendance.module.in_(module_names)
    ).order_by(Attendance.timestamp.desc()).limit(5).all()
    
    return render_template(
        'lecturer_dashboard.html',
        lecturer=lecturer,
        student_count=student_count,
        today_attendance=today_attendance,
        recent_attendance=recent_attendance,
        current_date=datetime.now(),
        faculties=FACULTIES,
        modules=faculty_modules
    )
@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        student_id = request.form['student_id'].strip()
        name = request.form['name'].strip()
        faculty = request.form.get('faculty', '').strip()
        course = request.form.get('course', '').strip()
        email = request.form.get('email', '').strip()
        phone = request.form.get('phone', '').strip()
        password = request.form['password'].strip()  # Add this line
        confirm_password = request.form['confirm_password'].strip()  # Add this line

        # Validation
        errors = []
        if not student_id.isdigit() or len(student_id) != 8:
            errors.append("Student ID must be exactly 8 digits")
        if phone and (not phone.isdigit() or len(phone) != 10):
            errors.append("Phone number must be exactly 10 digits")
        if password != confirm_password:  # Add password validation
            errors.append("Passwords do not match")
        if len(password) < 8:  # Add password strength validation
            errors.append("Password must be at least 8 characters")
            
        if errors:
            for error in errors:
                flash(error, 'error')
            return render_template('register.html', 
                                faculties=FACULTIES,
                                selected_faculty=faculty,
                                courses=FACULTIES.get(faculty, []),
                                selected_course=course)

        if Student.query.filter_by(student_id=student_id).first():
            flash('Student ID already exists!', 'error')
            return render_template('register.html', 
                                faculties=FACULTIES,
                                selected_faculty=faculty,
                                courses=FACULTIES.get(faculty, []),
                                selected_course=course)

        cap = cv2.VideoCapture(0)
        encodings = []
        face_detected = False
        
        for i in range(5):
            ret, frame = cap.read()
            if ret:
                rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                small_frame = cv2.resize(rgb_frame, (0, 0), fx=0.5, fy=0.5)
                face_locations = face_recognition.face_locations(small_frame, model="hog")
                
                if face_locations:
                    face_detected = True
                    top, right, bottom, left = [coord * 2 for coord in face_locations[0]]
                    face_image = frame[top:bottom, left:right]
                    face_image = cv2.cvtColor(face_image, cv2.COLOR_BGR2GRAY)
                    face_image = cv2.equalizeHist(face_image)
                    face_image = cv2.cvtColor(face_image, cv2.COLOR_GRAY2BGR)
                    
                    temp_img_path = f"static/encodings/{student_id}_temp_{i}.jpg"
                    cv2.imwrite(temp_img_path, face_image)
                    
                    image = face_recognition.load_image_file(temp_img_path)
                    face_encodings = face_recognition.face_encodings(image)
                    
                    if face_encodings:
                        encodings.append(face_encodings[0])
                    os.remove(temp_img_path)
                time.sleep(0.3)
        
        cap.release()
        
        if encodings:
            try:
                avg_encoding = np.mean(encodings, axis=0)
                np.save(f"static/encodings/{student_id}.npy", avg_encoding)
                
                img_path = f"static/encodings/{student_id}.jpg"
                cv2.imwrite(img_path, frame)
                
                new_student = Student(
                    student_id=student_id,
                    name=name,
                    faculty=faculty,
                    course=course,
                    email=email,
                    phone=phone,
                    password=password  # Add this line
                )
                db.session.add(new_student)
                db.session.commit()
                flash('Student registered successfully!', 'success')
                return redirect(url_for('view_student', student_id=student_id))
            except Exception as e:
                db.session.rollback()
                if os.path.exists(f"static/encodings/{student_id}.npy"):
                    os.remove(f"static/encodings/{student_id}.npy")
                if os.path.exists(f"static/encodings/{student_id}.jpg"):
                    os.remove(f"static/encodings/{student_id}.jpg")
                flash(f'Registration failed: {str(e)}', 'error')
        else:
            if face_detected:
                flash('Face detected but could not generate encodings. Please try again in better lighting.', 'error')
            else:
                flash('No face detected in any of the captures. Please try again.', 'error')
    
    return render_template('register.html', 
                         faculties=FACULTIES,
                         selected_faculty=None,
                         courses=[],
                         selected_course=None)

@app.route('/login_student', methods=['GET', 'POST'])
def login_student():
    if request.method == 'POST':
        student_id = request.form['student_id'].strip()
        password = request.form['password'].strip()
        
        student = Student.query.filter_by(student_id=student_id).first()
        
        if not student:
            flash('Invalid student ID or password', 'error')
            return redirect(url_for('login_student'))
            
        if student.password != password:  # In production, use password hashing
            flash('Invalid student ID or password', 'error')
            return redirect(url_for('login_student'))
            
        # Store student info in session
        session['student_id'] = student.student_id
        session['student_name'] = student.name
        
        flash(f'Welcome back, {student.name}!', 'success')
        return redirect(url_for('view_student', student_id=student.student_id))
    
    return render_template('login_student.html')

@app.route('/get_courses/<faculty>')
def get_courses(faculty):
    courses = FACULTIES.get(faculty, [])
    return jsonify(courses)

def gen_frames_attendance():
    cap = cv2.VideoCapture(0)
    while True:
        success, frame = cap.read()
        if not success:
            break
        
        rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        small_frame = cv2.resize(rgb_frame, (0, 0), fx=0.5, fy=0.5)
        face_locations = face_recognition.face_locations(small_frame, model="hog")
        face_locations = [(top*2, right*2, bottom*2, left*2) for (top, right, bottom, left) in face_locations]
        
        center_x, center_y = frame.shape[1]//2, frame.shape[0]//2
        cv2.circle(frame, (center_x, center_y), 100, (0, 255, 255), 2)
        cv2.putText(frame, "Position face here", (center_x-80, center_y-120), 
                   cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 255), 2)
        
        for (top, right, bottom, left) in face_locations:
            face_center_x = (left + right) // 2
            face_center_y = (top + bottom) // 2
            width = right - left
            height = bottom - top
            
            radius = int(min(width, height) * 0.6)
            cv2.circle(frame, (face_center_x, face_center_y), radius, (0, 255, 0), 2)
            
            for i in range(0, 360, 45):
                angle = np.deg2rad(i + (datetime.now().microsecond / 1000000) * 360)
                end_x = face_center_x + int(radius * np.cos(angle))
                end_y = face_center_y + int(radius * np.sin(angle))
                cv2.line(frame, (face_center_x, face_center_y), (end_x, end_y), (0, 255, 0), 1)
            
            cv2.rectangle(frame, (left, top), (right, bottom), (0, 255, 0), 2)
            cv2.putText(frame, "SCANNING", (left, top - 10), 
                       cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 1)
        
        ret, buffer = cv2.imencode('.jpg', frame)
        frame = buffer.tobytes()
        yield (b'--frame\r\n'
               b'Content-Type: image/jpeg\r\n\r\n' + frame + b'\r\n')

@app.route('/attendance', methods=['GET', 'POST'])
def mark_attendance():
    # Get all modules from database
    modules = Module.query.all()
    
    # Get statistics for template
    student_count = Student.query.count()
    today_attendance = Attendance.query.filter(
        db.func.date(Attendance.timestamp) == datetime.today().date()
    ).count()
    
    if request.method == 'POST':
        module_id = request.form.get('module', '').strip()
        if not module_id:
            flash('Please select a module', 'error')
            return render_template('attendance.html', 
                                modules=modules,
                                student_count=student_count,
                                today_attendance=today_attendance)
            
        module = Module.query.get(module_id)
        if not module:
            flash('Invalid module selected', 'error')
            return redirect(url_for('attendance'))
        
        known_encodings = []
        known_ids = []
        known_names = []
        missing_encodings = []

        students = Student.query.all()
        for student in students:
            enc_file = f"static/encodings/{student.student_id}.npy"
            if os.path.exists(enc_file):
                try:
                    encoding = np.load(enc_file)
                    known_encodings.append(encoding)
                    known_ids.append(student.student_id)
                    known_names.append(student.name)
                except Exception as e:
                    logging.error(f"Error loading encoding for {student.student_id}: {str(e)}")
                    missing_encodings.append(student.student_id)
            else:
                missing_encodings.append(student.student_id)
        
        if not known_encodings:
            flash('No valid face encodings found!', 'error')
            return redirect(url_for('attendance'))
            
        cap = cv2.VideoCapture(0)
        detected_students = set()
        recognition_results = []
        verification_frames_required = 5
        min_confidence = 0.65
        
        try:
            start_time = datetime.now()
            verification_counts = {}
            
            while (datetime.now() - start_time).seconds < 20:
                ret, frame = cap.read()
                if not ret:
                    continue
                
                rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                small_frame = cv2.resize(rgb_frame, (0, 0), fx=0.5, fy=0.5)
                face_locations = face_recognition.face_locations(small_frame, model="hog")
                face_locations = [(top*2, right*2, bottom*2, left*2) for (top, right, bottom, left) in face_locations]
                face_encodings = face_recognition.face_encodings(rgb_frame, face_locations)
                
                for (top, right, bottom, left), face_encoding in zip(face_locations, face_encodings):
                    face_center_x = (left + right) // 2
                    face_center_y = (top + bottom) // 2
                    frame_center_x, frame_center_y = frame.shape[1]//2, frame.shape[0]//2
                    
                    if (abs(face_center_x - frame_center_x) > 100 or 
                        abs(face_center_y - frame_center_y) > 100):
                        cv2.putText(frame, "PLEASE CENTER FACE", 
                                  (left, top - 10), cv2.FONT_HERSHEY_SIMPLEX, 
                                  0.5, (0, 0, 255), 2)
                        continue
                    
                    face_distances = face_recognition.face_distance(known_encodings, face_encoding)
                    best_match_index = np.argmin(face_distances)
                    confidence = 1 - face_distances[best_match_index]
                    
                    if confidence >= min_confidence:
                        student_id = known_ids[best_match_index]
                        student_name = known_names[best_match_index]
                        
                        if student_id not in verification_counts:
                            verification_counts[student_id] = {'count': 0, 'min_confidence': confidence}
                        else:
                            verification_counts[student_id]['count'] += 1
                            verification_counts[student_id]['min_confidence'] = min(
                                verification_counts[student_id]['min_confidence'], confidence
                            )
                        
                        cv2.rectangle(frame, (left, top), (right, bottom), (255, 255, 0), 2)
                        cv2.putText(frame, f"VERIFYING: {student_name}", 
                                  (left, top - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 0), 1)
                        cv2.putText(frame, f"Confidence: {confidence*100:.1f}%", 
                                  (left, bottom + 20), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 0), 1)
                        
                        if (verification_counts[student_id]['count'] >= verification_frames_required and 
                            verification_counts[student_id]['min_confidence'] >= min_confidence):
                            if student_id not in detected_students:
                                student = Student.query.filter_by(student_id=student_id).first()
                                
                                existing = Attendance.query.filter(
                                    Attendance.student_id == student_id,
                                    db.func.date(Attendance.timestamp) == datetime.today().date(),
                                    Attendance.module == module.name  # Fixed: Use module.name instead of modules
                                ).first()
                                
                                if existing:
                                    time_since_last = datetime.now() - existing.timestamp
                                    if time_since_last.total_seconds() < 300:
                                        cv2.rectangle(frame, (left, top), (right, bottom), (0, 165, 255), 2)
                                        cv2.putText(frame, "ALREADY MARKED TODAY", 
                                                  (left, top - 10), cv2.FONT_HERSHEY_SIMPLEX, 
                                                  0.5, (0, 165, 255), 2)
                                        cv2.putText(frame, f"Last: {existing.timestamp.strftime('%H:%M:%S')}", 
                                                  (left, bottom + 20), cv2.FONT_HERSHEY_SIMPLEX, 
                                                  0.5, (0, 165, 255), 1)
                                        cv2.imshow('Attendance System', frame)
                                        cv2.waitKey(2000)
                                        continue
                                
                                cv2.rectangle(frame, (left, top), (right, bottom), (0, 255, 0), 2)
                                cv2.putText(frame, f"VERIFIED: {student.name}", 
                                          (left, top - 10), cv2.FONT_HERSHEY_SIMPLEX, 
                                          0.5, (0, 255, 0), 2)
                                
                                cv2.imshow('Attendance System', frame)
                                cv2.waitKey(1000)
                                
                                db.session.add(Attendance(
                                    student_id=student_id,
                                    name=student.name,
                                    module=module.name  # Fixed: Use module.name instead of modules
                                ))
                                db.session.commit()
                                
                                detected_students.add(student_id)
                                recognition_results.append({
                                    'name': student.name,
                                    'student_id': student_id,
                                    'time': datetime.now().strftime("%H:%M:%S"),
                                    'confidence': f"{confidence*100:.1f}%"
                                })
                                logging.info(f"Attendance marked for {student.name} (ID: {student_id}) with confidence {confidence*100:.1f}%")
                    else:
                        cv2.rectangle(frame, (left, top), (right, bottom), (0, 0, 255), 2)
                        cv2.putText(frame, "UNKNOWN FACE", 
                                  (left, top - 10), cv2.FONT_HERSHEY_SIMPLEX, 
                                  0.5, (0, 0, 255), 2)
                        logging.debug(f"Unknown face detected (confidence: {confidence*100:.1f}%)")
                
                cv2.imshow('Attendance System', frame)
                if cv2.waitKey(1) & 0xFF == ord('q'):
                    break
            
            cv2.destroyAllWindows()
            
            if recognition_results:
                success_messages = []
                for result in recognition_results:
                    msg = Markup(
                        f'<div class="recognition-success">'
                        f'<i class="fas fa-check-circle"></i> '
                        f'<strong>{result["name"]}</strong> (ID: {result["student_id"]}) '
                        f'verified at {result["time"]} (Confidence: {result["confidence"]})'
                        f'</div>'
                    )
                    success_messages.append(msg)
                
                flash(Markup('<div class="recognition-results">' + ''.join(success_messages) + '</div>'), 'success')
            else:
                flash('No verified students detected!', 'warning')
                
        except Exception as e:
            logging.error(f"Face recognition error: {str(e)}")
            flash('Face recognition error occurred', 'error')
        finally:
            cap.release()
            cv2.destroyAllWindows()
        
        return redirect(url_for('view_attendance'))
    
    return render_template('attendance.html',
                         modules=modules,
                         student_count=student_count,
                         today_attendance=today_attendance)
@app.route('/view')
def view_attendance():
    page = request.args.get('page', 1, type=int)
    module_filter = request.args.get('module', '')
    date_filter = request.args.get('date', '')
    
    query = Attendance.query
    
    # Apply filters if provided
    if module_filter:
        query = query.filter(Attendance.module == module_filter)
    if date_filter:
        try:
            filter_date = datetime.strptime(date_filter, '%Y-%m-%d').date()
            query = query.filter(db.func.date(Attendance.timestamp) == filter_date)
        except ValueError:
            flash('Invalid date format. Please use YYYY-MM-DD', 'error')
    
    # Get unique module names from attendance records
    module_names = db.session.query(Attendance.module.distinct()).all()
    module_names = [m[0] for m in module_names]
    
    # Order by timestamp and paginate
    records = query.order_by(Attendance.timestamp.desc()).paginate(
        page=page, 
        per_page=5, 
        error_out=False
    )
    
    return render_template(
        'view.html',
        records=records,
        modules=module_names,  # Pass the list of module names
        selected_module=module_filter,
        selected_date=date_filter
    )

@app.route('/students')
def list_students():
    students = Student.query.all()
    return render_template('students.html', students=students)

@app.route('/video_feed')
def video_feed():
    return Response(gen_frames(), mimetype='multipart/x-mixed-replace; boundary=frame')

@app.route('/video_feed_attendance')
def video_feed_attendance():
    return Response(gen_frames_attendance(), mimetype='multipart/x-mixed-replace; boundary=frame')

@app.route('/delete_student/<string:student_id>', methods=['POST'])
def delete_student(student_id):
    try:
        student = Student.query.filter_by(student_id=student_id).first()
        if not student:
            flash('Student not found!', 'error')
            return redirect(url_for('list_students'))

        face_image = f"static/encodings/{student_id}.jpg"
        face_encoding = f"static/encodings/{student_id}.npy"
        
        if os.path.exists(face_image):
            os.remove(face_image)
        if os.path.exists(face_encoding):
            os.remove(face_encoding)

        Attendance.query.filter_by(student_id=student_id).delete()
        db.session.delete(student)
        db.session.commit()
        
        flash(f'Student {student.name} deleted successfully!', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error deleting student: {str(e)}', 'error')
    
    return redirect(url_for('list_students'))

# Add these new routes to your app.py

# Update the view_student route to include a link to the calendar
@app.route('/student/<string:student_id>')
def view_student(student_id):
    student = Student.query.filter_by(student_id=student_id).first_or_404()

    if 'student_id' in session and session['student_id'] == student_id:
        # Get today's modules for the student's faculty
        today = datetime.now().date()
        today_modules = Module.query.filter_by(faculty=student.faculty).all()
        
        # For demo, let's just show all modules for the faculty
        # In a real system, you'd filter by day of week
        return render_template('view_student.html', 
                             student=student,
                             today_modules=today_modules)
    else:
        flash('Please login to view your profile', 'error')
        return redirect(url_for('login_student'))

@app.route('/edit_student/<string:student_id>', methods=['GET', 'POST'])
def edit_student(student_id):
    student = Student.query.filter_by(student_id=student_id).first_or_404()
    
    if request.method == 'POST':
        # Update student information
        student.name = request.form['name'].strip()
        student.faculty = request.form.get('faculty', '').strip()
        student.course = request.form.get('course', '').strip()
        student.email = request.form.get('email', '').strip()
        student.phone = request.form.get('phone', '').strip()
        
        # Phone validation (must be 10 digits)
        if student.phone and (not student.phone.isdigit() or len(student.phone) != 10):
            flash("Phone number must be exactly 10 digits", 'error')
            return render_template('edit_student.html', 
                                student=student,
                                faculties=FACULTIES,
                                courses=FACULTIES.get(student.faculty, []))
        
        try:
            db.session.commit()
            flash('Student updated successfully!', 'success')
            return redirect(url_for('view_student', student_id=student.student_id))
        except Exception as e:
            db.session.rollback()
            flash(f'Error updating student: {str(e)}', 'error')
    
    return render_template('edit_student.html', 
                         student=student,
                         faculties=FACULTIES,
                         courses=FACULTIES.get(student.faculty, []))



@app.route('/download_attendance')
def download_attendance():
    # Get filters from query parameters
    module_filter = request.args.get('module', '')
    date_filter = request.args.get('date', '')
    
    query = Attendance.query
    
    # Apply the same filters as the view page
    if module_filter:
        query = query.filter(Attendance.module == module_filter)
    if date_filter:
        try:
            filter_date = datetime.strptime(date_filter, '%Y-%m-%d').date()
            query = query.filter(db.func.date(Attendance.timestamp) == filter_date)
        except ValueError:
            flash('Invalid date format', 'error')
            return redirect(url_for('view_attendance'))
    
    records = query.order_by(Attendance.timestamp.desc()).all()
    
    # Create a new Excel workbook
    wb = Workbook()
    ws = wb.active
    ws.title = "Attendance Records"
    
    # Add headers
    headers = ["Student ID", "Name", "Module", "Date", "Time"]
    ws.append(headers)
    
    # Add data rows
    for record in records:
        ws.append([
            record.student_id,
            record.name,
            record.module,
            record.timestamp.strftime('%Y-%m-%d'),
            record.timestamp.strftime('%H:%M:%S')
        ])
    
    # Style the header row
    for cell in ws[1]:
        cell.font = cell.font.copy(bold=True)
    
    # Create a BytesIO buffer and save the workbook
    buffer = BytesIO()
    wb.save(buffer)
    buffer.seek(0)
    
    # Create the download response
    filename = "attendance_records.xlsx"
    if module_filter:
        filename = f"attendance_{module_filter.replace(' ', '_')}.xlsx"
    if date_filter:
        filename = f"attendance_{date_filter}.xlsx"
    if module_filter and date_filter:
        filename = f"attendance_{module_filter.replace(' ', '_')}_{date_filter}.xlsx"
    
    return Response(
        buffer,
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment;filename={filename}"}
    )
@app.route('/logout_lecturer')
def logout_lecturer():
    session.pop('lecturer_id', None)
    session.pop('lecturer_name', None)
    session.pop('lecturer_faculty', None)
    flash('You have been logged out successfully', 'success')
    return redirect(url_for('home'))

@app.route('/logout_student')
def logout_student():
    session.pop('student_id', None)
    session.pop('student_name', None)
    flash('You have been logged out successfully', 'success')
    return redirect(url_for('home'))

# Add this route for the student calendar
@app.route('/student_calendar')
def student_calendar():
    if 'student_id' not in session:
        flash('Please login first', 'error')
        return redirect(url_for('login_student'))
    
    student = Student.query.filter_by(student_id=session['student_id']).first()
    if not student:
        session.clear()
        flash('Student not found', 'error')
        return redirect(url_for('login_student'))
    
    # Get current week
    now = datetime.now()
    start_of_week = now - timedelta(days=now.weekday())
    
    # Generate the week days
    week_days = []
    for i in range(7):
        day = start_of_week + timedelta(days=i)
        week_days.append(day)
    
    # Get modules for the student's faculty
    modules = Module.query.filter_by(faculty=student.faculty).all()
    
    # Create a 2D grid for the schedule: days (0-6) x hours (8-17)
    schedule_grid = {day_index: {hour: [] for hour in range(8, 18)} for day_index in range(7)}
    
    # Place each module in its correct time slot
    for module in modules:
        day_index = module.day_of_week
        start_hour = module.start_time.hour
        end_hour = module.end_time.hour
        
        # Place the module in its starting hour slot only
        if start_hour in schedule_grid[day_index]:
            schedule_grid[day_index][start_hour].append(module)
    
    return render_template('student_calendar.html', 
                         student=student,
                         week_days=week_days,
                         schedule_grid=schedule_grid,
                         current_date=now)
# Add this at the bottom of your app.py before running
if __name__ == '__main__':   
    app.run(debug=True)
