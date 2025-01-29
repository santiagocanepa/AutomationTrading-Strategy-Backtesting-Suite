import { readFileSync, writeFileSync, existsSync } from 'fs';
import { join } from 'path';

interface ResultData {
    id: string;
    name: string;  
    combination: any;
    result: { [key: string]: string | undefined };
    jsonFileName: string;  
}

export async function appendResultToFile(data: ResultData): Promise<void> {
    const resultsDir = process.env.RESULTS_DIR || './Results';
    const filePath = join(resultsDir, data.jsonFileName);
    let results = {};

    if (existsSync(filePath)) {
        const fileData = readFileSync(filePath, 'utf-8');
        results = JSON.parse(fileData);
    }

    (results as any)[data.id] = {
        name: data.name,
        combination: data.combination,
        result: data.result
    };

    writeFileSync(filePath, JSON.stringify(results, null, 2));
}
