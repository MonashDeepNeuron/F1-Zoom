import { BrowserRouter, Routes, Route } from "react-router-dom";
import "./App.css";
import Home from "./pages/Home";
import Live from "./pages/Live";
import Predictions from "./pages/Predictions";
import "bootstrap/dist/css/bootstrap.min.css";

function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<Home />} />
        <Route path="/live" element={<Live />} />
        <Route path="/predictions" element={<Predictions />} />
      </Routes>
    </BrowserRouter>
  );
}

export default App;
