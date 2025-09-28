async function sendJsonFile() {
  const file = new File(
    [JSON.stringify({ test: "hello", id: 1 })],
    "sample.json",
    { type: "application/json" }
  );

  const formData = new FormData();
  formData.append("file", file);

  const response = await fetch("http://localhost:3000/upload-json", {
    method: "POST",
    body: formData
  });

  const result = await response.json();
  console.log(result);
}
