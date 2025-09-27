// Function to generate floating shapes on the background
function generateFloatingShapes() {
  const shapeContainer = document.querySelector('.floating-shapes');

  // Optional: Clear previous shapes if regenerating
  shapeContainer.innerHTML = '';

  const numShapes = 13;

  for (let i = 0; i < numShapes; i++) {
    const shape = document.createElement('div');
    shape.classList.add('shape');

    // Random size between 5vw and 10vw (scales with screen width)
    const sizeVW = Math.random() * 5 + 5; // 5vw to 10vw
    shape.style.width = `${sizeVW}vw`;
    shape.style.height = `${sizeVW}vw`; // Square

    // Random position using percentages
    shape.style.top = `${Math.random() * 100}%`;
    shape.style.left = `${Math.random() * 100}%`;

    // Random animation properties
    shape.style.animationDuration = `${Math.random() * 5 + 5}s`; // 5s to 10s
    shape.style.animationDelay = `${Math.random() * 5}s`; // 0s to 5s

    shapeContainer.appendChild(shape);
  }
}


// Event listener for sign-up form submission
document.getElementById('signup-form')?.addEventListener('submit', function(event) {
  event.preventDefault(); // Prevent the default form submission

  const name = document.getElementById('name').value;
  const email = document.getElementById('email').value;
  const phone = document.getElementById('phone').value;
  const password = document.getElementById('password').value;

  // Example validation (you can improve this)
  if (name && email && phone && password) {
    alert('Sign-Up Successful! Redirecting to Message Page...');
    window.location.href = "message.html"; // Redirect to message page
  } else {
    alert('Please fill out all fields.');
  }
});

// Event listener for message form submission
document.getElementById('message-form')?.addEventListener('submit', function(event) {
  event.preventDefault(); // Prevent the default form submission

  const message = document.getElementById('message').value;

  if (message) {
    alert('Message Sent! Thank you for reaching out.');
  } else {
    alert('Please enter a message.');
  }
});

// Initialize floating shapes
generateFloatingShapes();


window.addEventListener('DOMContentLoaded', () => {
  const dateInput = document.getElementById('reminder-date');
  const timeInput = document.getElementById('reminder-time');

  const now = new Date();

  // Format today's date as yyyy-mm-dd
  const todayStr = now.toISOString().split('T')[0];
  dateInput.min = todayStr;

  // Update time options dynamically based on selected date
  dateInput.addEventListener('change', () => {
    const selectedDate = new Date(dateInput.value);
    const now = new Date();

    // If today is selected, restrict time to future hours only
    if (dateInput.value === todayStr) {
      const currentHour = now.getHours();
      const nextHour = currentHour + 1;

      // Set min to next full hour
      timeInput.min = `${nextHour.toString().padStart(2, '0')}:00`;
    } else {
      // If it's a future date, allow all times
      timeInput.min = '00:00';
    }
  });

  // Validate on form submit
  document.getElementById('message-form')?.addEventListener('submit', function (event) {
    event.preventDefault();

    const message = document.getElementById('message').value;
    const date = dateInput.value;
    const time = timeInput.value;

    const selectedDateTime = new Date(`${date}T${time}`);
    const now = new Date();

    if (!message || !date || !time) {
      alert('Please fill out all fields.');
      return;
    }

    if (selectedDateTime <= now) {
      alert('Please choose a future date and time.');
      return;
    }

    alert(`Reminder Set!\n\nMessage: ${message}\nDate: ${date}\nTime: ${time}`);
  });
});


document.getElementById('hamburger-menu')?.addEventListener('click', () => {
  const menu = document.getElementById('dropdown-menu');
  const hamburger = document.getElementById('hamburger-menu');

  // Toggle menu display
  if (menu.style.display === 'block') {
    menu.style.display = 'none';
    hamburger.classList.remove('active');
  } else {
    menu.style.display = 'block';
    hamburger.classList.add('active');
  }
});


// Optional: Close menu when clicking outside
document.addEventListener('click', (e) => {
  const menu = document.getElementById('dropdown-menu');
  const hamburger = document.getElementById('hamburger-menu');
  
  if (!hamburger.contains(e.target) && !menu.contains(e.target)) {
    menu.style.display = 'none';
  }
});

document.addEventListener("DOMContentLoaded", function () {
  const form = document.getElementById("message-form");
  const historyList = document.getElementById("conversation-history");

  // Optional: Store history in localStorage
  let reminders = JSON.parse(localStorage.getItem("reminders")) || [];

  function renderHistory() {
    historyList.innerHTML = "";
    reminders.forEach((item, index) => {
      const li = document.createElement("li");
      li.textContent = `${item.date} at ${item.time} — ${item.message}`;
      historyList.appendChild(li);
    });
  }

  form.addEventListener("submit", function (e) {
    e.preventDefault();

    const message = document.getElementById("message").value;
    const date = document.getElementById("reminder-date").value;
    const time = document.getElementById("reminder-time").value;

    if (!message || !date || !time) return;

    const reminder = { message, date, time };
    reminders.push(reminder);

    // Save to localStorage
    localStorage.setItem("reminders", JSON.stringify(reminders));

    // Reset form
    form.reset();

    // Re-render history
    renderHistory();
  });

  // Initial render
  renderHistory();
});

document.addEventListener("DOMContentLoaded", function () {
  const form = document.getElementById("message-form");
  const historyList = document.getElementById("conversation-history");
  const clearButton = document.getElementById("clear-history");

  let reminders = JSON.parse(localStorage.getItem("reminders")) || [];

  function renderHistory() {
    historyList.innerHTML = "";

    if (reminders.length === 0) {
      const empty = document.createElement("li");
      empty.textContent = "No reminders yet.";
      historyList.appendChild(empty);
      return;
    }

    reminders.forEach((item) => {
      const li = document.createElement("li");
      li.textContent = `${item.date} at ${item.time} — ${item.message}`;
      historyList.appendChild(li);
    });
  }

  form.addEventListener("submit", function (e) {
    e.preventDefault();

    const message = document.getElementById("message").value;
    const date = document.getElementById("reminder-date").value;
    const time = document.getElementById("reminder-time").value;

    if (!message || !date || !time) return;

    const reminder = { message, date, time };
    reminders.push(reminder);
    localStorage.setItem("reminders", JSON.stringify(reminders));
    form.reset();
    renderHistory();
  });

  clearButton.addEventListener("click", function () {
    if (confirm("Are you sure you want to clear all reminders?")) {
      reminders = [];
      localStorage.removeItem("reminders");
      renderHistory();
    }
  });

  renderHistory();
});

document.getElementById('message-form').addEventListener('submit', function (e) {
  e.preventDefault();

  const message = document.getElementById('message').value;
  const date = document.getElementById('reminder-date').value;
  const time = document.getElementById('reminder-time').value;

  // Ask for user's phone number (or get it from a hidden field or login)
  const phone = prompt('Enter your phone number (in E.164 format, e.g., +1234567890):');

  fetch('http://localhost:3000/send-reminder', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json'
    },
    body: JSON.stringify({ message, date, time, phone })
  })
    .then(res => res.json())
    .then(data => {
      if (data.success) {
        alert('Reminder sent via SMS!');
      } else {
        alert('Failed to send SMS: ' + data.error);
      }
    })
    .catch(err => {
      console.error('Error:', err);
      alert('An error occurred while sending the reminder.');
    });
});
