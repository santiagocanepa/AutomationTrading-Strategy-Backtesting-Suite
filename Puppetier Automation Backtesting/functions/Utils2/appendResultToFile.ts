import { readFileSync, writeFileSync, existsSync } from 'fs';
import { join } from 'path';

interface ResultData {
    id: string;
    name: string;  // Incluir el nombre de la combinación
    combination: any;
    result: { [key: string]: string | undefined };
    jsonFileName: string;  // Agregar jsonFileName a la interfaz
}

export async function appendResultToFile(data: ResultData): Promise<void> {
    const resultsDir = process.env.RESULTS_DIR || './Results';
    const filePath = join(resultsDir, data.jsonFileName);
    let results = {};

    // Si el archivo ya existe, leer su contenido
    if (existsSync(filePath)) {
        const fileData = readFileSync(filePath, 'utf-8');
        results = JSON.parse(fileData);
    }

    // Agregar el nuevo resultado al objeto de resultados, incluyendo el nombre de la combinación
    (results as any)[data.id] = {
        name: data.name,
        combination: data.combination,
        result: data.result
    };

    // Escribir el objeto de resultados actualizado de nuevo en el archivo
    writeFileSync(filePath, JSON.stringify(results, null, 2));
}
