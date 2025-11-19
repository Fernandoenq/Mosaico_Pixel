@echo off
chcp 65001 >nul
echo ========================================
echo  📸 Criador de Vídeo de Álbum de Fotos
echo ========================================
echo.

echo [1/3] Verificando Python...
python --version >nul 2>&1
if errorlevel 1 (
    echo ❌ Python não encontrado! Por favor instale o Python primeiro.
    echo    Baixe em: https://www.python.org/downloads/
    pause
    exit /b 1
)
echo ✅ Python encontrado!
echo.

echo [2/3] Instalando dependências...
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
if errorlevel 1 (
    echo ❌ Erro ao instalar dependências!
    pause
    exit /b 1
)
echo ✅ Dependências instaladas!
echo.

echo [3/3] Criando vídeo...
echo.
python criar_video_album.py
if errorlevel 1 (
    echo.
    echo ❌ Erro ao criar vídeo!
    pause
    exit /b 1
)

echo.
echo ========================================
echo  ✅ Processo concluído!
echo  📹 Vídeo salvo como: album_fotos.mp4
echo ========================================
echo.
pause

