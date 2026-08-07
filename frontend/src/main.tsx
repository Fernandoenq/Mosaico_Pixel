import React from 'react';
import ReactDOM from 'react-dom/client';
import { BrowserRouter, Routes, Route } from 'react-router-dom';
import App from './App';
import MosaicoAoVivo from './pages/MosaicoAoVivo';
import './index.css';

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<App />} />
        <Route path="/mosaicoaovivo" element={<MosaicoAoVivo />} />
      </Routes>
    </BrowserRouter>
  </React.StrictMode>
);
