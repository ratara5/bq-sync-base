EN MÁQUINA LOCAL: CONSTRUIR Y SUBIR IMAGEN  
(se puede incluir esto en 'create-company-gci.sh'?)  
# PROBAR EL FUNCIONAMIENTO DEL PROYECTO (PREVIO A DOCKERIZAR)  

## 1. CONSTRUIR EL AMBIENTE VIRTUAL Y LEVANTAR LA BASE DE DATOS (QUE SÍ ESTÁ DOCKERIZADA)  
```PROJECT_ROOT = ~/Documents/GoogleCloudProjects```

```bash
export PR_PATH=~/Documents/GoogleCloudProjects
cd "$PR_PATH/gci-companies/gci-base/bq-sync-base"
./bootstrap.sh \
    --project-root $PR_PATH \
    --compose-file docker-compose.yml \
    --init-file init.sql
```  

## 2. DEPURAR LA APP  
**a**  Asegurar que el ```${workspaceFolder}``` sea el directorio que contenga a ```app/``` en su primer nivel  
**b**  Escribir ```.vscode/launch.json```  así:

```.json
{
    "version": "0.2.0",
    "configurations": [
        {
            "type": "python",
            "request": "launch",
            "name": "app debug",
            "program": "${workspaceFolder}/app/main.py",
            "cwd": "${workspaceFolder}/app",
            "envFile": "${workspaceFolder}/app/.env",
            "console": "integratedTerminal",
            "justMyCode": false
        }
    ]
}
```
**c**  Correr la app en modo debugg con ```Ctrl + F5```  

## 3. CORRER LA APP  
```bah
export PR_PATH=~/Documents/GoogleCloudProjects
cd "$PR_PATH/gci-companies/gci-base/bq-sync-base"
source venv/bin/activate
cd app
python3.12 main.py
```  

**Invocar rutas**  
```bash
curl http://localhost:5555/health
```  

```bash
curl -X POST http://localhost:5555/sync/transaccional_upsert
```  





# CONTRUIR Y SUBIR LA IMAGEN A PARTIR DEL PROYECTO  
1. Moverse al directorio de la gci-base/gmsync-base
```bash
cd ~/Documents/GoogleCloudProjects/gci-companies/gci-base/bq-sync-base
```  

2. Login en GHCR.IO - Github container registry (desde terminal)  
```CR_PAT``` <>= GitHub Personal Access Token con scope ```read:packages``` / ```write:packages```.

```bash
export CR_PAT=ghp_TokenAqui
```` 

```bash
echo $CR_PAT | docker login ghcr.io -u GITHUB_USERNAME --password-stdin
```  

3. Construir la imagen  
```bash
docker build -f Dockerfile -t ghcr.io/GITHUB_USERNAME/image-name:1.0.0 .
```  

Se pueden revisar las imágenes docker disponibles en el sistema
```bash
docker image ls
```  

4. Subir imagen GHCR.IO
```bash
docker push ghcr.io/GITHUB_USERNAME/image-name:1.0.0
```  
Se puede verificar que la imagen está en Docker Hub visitando  
https://github.com/GITHUB_USERNAME?tab=packages

5. Cerrar sesión GHCR.IO
```bash
docker logout ghcr.io
``` 